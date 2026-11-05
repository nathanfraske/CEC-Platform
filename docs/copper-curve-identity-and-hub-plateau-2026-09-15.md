# Exact curve preservation before inherited-cell ownership work

## Finished Hub continuation

`build/return-continuation-suite-20260915/suite.json` finished **22:23:20Z**,
314.13 worker seconds. All source/hierarchy/engine guards passed and every
descendant exited. The output is **ab70d2fca1f5**, still **four placement-craft
blockers**. Two accepted C28 moves reduce its reported supply distance from
1.32 to 1.29 mm, but clear no hard blocker. It never entered main routing.
This is a plateau for this slice: do not schedule another unchanged Hub pass.

The completed immutable review was API-verified and visually inspected:
`pass-return-continuation-suite-20260915-hub-standard-rev2-7272998437`.
Windows mirror:
`C:/Users/Admin/Documents/CEC-Board-Reviews/return-continuation-suite-20260915/hub-standard-rev2/render.png`.
The caption correctly says placement/BLOCKED/NOT FAB SIGNOFF. Do not present
its nearly unchanged preview as a newly routed board.

Explicit retained inputs now live in
`build/copper-curve-next-inputs-20260915.json`: verified completed Hub ab70,
the same five other current source identities, no automatic promotion or
permission to dispatch another unchanged retry. Their independent holds remain.

## Generic guard defect and repair

Investigation of safe inherited-copper ownership found a real omission in
`cec_fr._copper_geometry_rows`. Its exact signature and locked-prefix contract
encoded an arc as its unordered endpoints, width, layer and native type, but
omitted its midpoint. An opposite-bowing arc with the same endpoints therefore
passed the purported exact-geometry guard. Native electrical connectivity is
a different check and cannot establish that retained copper was not reshaped.

The shared row encoder now includes both native integer midpoint coordinates
for `PCB_ARC`. Both exact-net signatures and immutable-prefix checks consume
that one encoder. Straight tracks and vias retain their previous encoding;
endpoint direction/order and UUID rewriting remain irrelevant to geometry.
Multiplicity still matters, and adding same-net copper does not replace an
existing retained arc. Production placement-resume admission is covered too.

Legacy chord-only arc evidence fails closed. It must be explicitly rebuilt
from its verified original artifact, not silently recaptured from the current
output. This slice does not implement that migration, grant local-cell unlock
authority, change power geometry, or claim an audit of every via-padstack field.

## Validation

- An isolated negative control reinstates the old encoder in memory, without
  editing production files: **all six translated/rotated/front/back rebowing
  cases fail** the new assertions (`copper-curve-identity-negative-control-20260915.log`).
- Final integration: **212 passed, no skips**, 97.42 s, one native-API
  deprecation warning (`copper-curve-identity-final-tests-20260915.log`).
  Coverage includes native curve reversal, multiplicity, extensions, legacy
  evidence refusal, production placement admission, pair replacement receipts,
  frozen copper, local power, full pipeline and generalization.
- The initial test run exposed a test-fixture mistake: KiCad vector getters
  return live references, so reversal now copies their integer values first.
  An older test also expected a diagnostic wording that predates the combined
  copper/pair guard; only its error-message regex was corrected. Neither change
  relaxes geometry admission. Initial failing logs are retained.
- `build/copper-curve-final-suite-replay-20260915/report.json`: six explicit
  source lineages in three native workers, including latest Hub ab70. Every
  source/hierarchy/engine guard passes. These particular boards contain no
  route arcs, so old/new primitive encodings are identical and new prefix
  self-checks pass. This is preventative hardening, **not a repair of their
  present routing blockers**. Interface-held boards get identity inspection
  only, not downstream route admission.
- Generality passes with zero core violations. Historical PCIe2 board bytes,
  complete regression and probes remain identical; only generalization metadata
  differs (`build/copper-curve-control-comparison-20260915.json`). Existing
  fabrication release holds remain, explaining the control command's exit 1.

## Next distinct work

There are no live board cohorts at this receipt. Check process state before
editing or dispatching. Do not launch more waves merely because this guard
changed: it cannot improve arc-free boards' current route searches.

PCIe2 still needs durable, content-bound ownership and qualified replacement of
**complete generated local cells** across continuation boundaries. That is NOT
implemented by this slice; named groups alone still do not authorize unlocking
the 60 inherited blockers. Require complete source identity, cell dependencies,
native locality/connectivity/DRC and full-score rollback before any such release.
VHP's USB escape, PCIe3's terminal-order/reach search, and EPS/ATX's coupled
terminal geometry are independent alternatives. Hub needs a distinct placement
cause addressed before another bounded full pass. No source schematic, load
budget, footprint, mating transform, or fixed power bus was changed.
