# Exact copper echo reconciliation — 2026-09-14

## Result and limits

The prior canonical PCIe2 continuation completed in 638.77 seconds without an
eligible routed output. Both seeds failed import sanitation, not placement or
route preflight. Replaying those exact failed imports with the generic repair
now passes the unchanged admission gate: **0 DRC / 12 opens**, Kelvin and
differential-pair gates true, no route-topology fault nets. This is an import
boundary repair, not a claim that the twelve opens have been routed.

The failed-run publisher correctly produced a `no-trustworthy-output` review;
that placeholder must not be presented as a completed board. The latest
previously published trusted candidate remains
[the local-via reconstruction](http://localhost:8090/?id=20260914-pcie2-local-via-rebuilt).

## Forensic cause

The raw imported artifact retained the original Kelvin copper UUIDs and added
exact same-net, same-layer, same-width copies. Two copied sections on the
reported sense net produced `covered_backtrack` topology failures. Native DRC
alone did not classify these copies as structural violations. The existing
sanitizer only removed proposal-owned items named by structural DRC, so it
could reach zero DRC while still failing the Kelvin/topology gate.

The complete replay found 18 exact copper copies in seed 0 and 10 in seed 1,
not just the two segments named by the critical-net topology report. The
archived artifact proves their presence after import-side processing; it does
not by itself prove whether each was emitted by SES or an import-side producer.
The live importer now records both boundaries separately to distinguish them.
Freerouting's `-noecho` option is not treated as proof of the final artifact.

## Reusable rule

`cec_copper_echo` compares all serialized fabrication fields, including net,
layer/span, width, drill, arc midpoint, mask and unknown future fields. Numeric
values compare exactly, without geometric tolerances. Endpoint reversal is
equivalent; UUID and lock state are not copper geometry.

- Remove only a newly introduced identity with an unchanged, surviving source
  counterpart. Never remove or reconstruct that original.
- Keep partial-net extensions, near overlaps, changed-width/drill/layer items,
  replacements for missing originals, and group-owned new proposals.
- Preserve source files, project settings, groups, placement and zones.
- Apply immediately after native SES import and after all import-side
  producers. Repeat defensively inside transactional sanitation for alternate
  backends and archived imports.
- All independent DRC, connectivity, Kelvin, pair and prefix admission remain
  mandatory. Failed admission still rolls the candidate back byte-for-byte.

The unused legacy whole-net reconciliation function was not enabled: its
rounded coordinate matching and whole-net ownership assumptions are not an
acceptable substitute for this exact identity-scoped rule.

## Verification

- `build/copper-echo-integrated-tests-20260914.log`: **112 passed**, plus 15
  parameterized subtests. Includes translated/rotated geometry, native board
  deletion, mask/unknown fields, via padstacks, arc direction, identity/group
  refusals, idempotence and rollback integration.
- `build/copper-echo-replay-20260914-final/receipt.json`: both archived failed
  imports accepted, original sources unchanged, engine hash set unchanged
  during the replay. About 22 seconds per archived replay; this is not a
  comparable full-pipeline speedup.
- All six current, hash-bound board inputs pass the no-op byte-preservation
  check. Injected exact copies were correctly removed on all four inputs with
  existing root copper: Hub, 12VHPWR, ATX and PCIe2. EPS and PCIe3 inputs had no
  root copper to inject; those are no-op coverage only. No interface ECO gate
  was bypassed by these disposable copy tests.
- `build/copper-echo-control-20260914.json`: historical PCIe2 board SHA, all four
  probe objects, and board-regression result exactly match the preceding
  control. Its broader pre-existing release blockers are not newly certified.
- `build/copper-echo-generalization-20260914.json`: 59 declared neutral modules,
  zero core violations. Whole-pipeline generic maturity remains **false**;
  23 legacy physical selectors and 380 runtime selectors remain reported.
- `git diff --check` passed. WSL had about 72 GiB free; 16 GiB floor retained.

## Live continuation and remaining suite work

`build/copper-echo-route-followup-20260914/suite.json` is the bounded canonical
producer replay, started from the same admitted source SHA
`82f98e64bc47ad32e7e7333c669b4944db56b97d3c2a89d11a964a3cddd692ba`.
Use its journal/process record for current status. At this note's creation,
placement passed in 31.0 seconds and route preflight was running. No result is
assumed. Do not start a duplicate or edit shared engine code while it runs.

The other five boards did not receive new full routing waves in this slice.
Their unchanged failures need another generic repair before another exhausted
wave is useful:

| Board | Known remaining barrier |
| --- | --- |
| Hub | Power-terminal access conflicts with an owned priority signal prefix; needs coordinated replacement and reproof, not bus displacement |
| 12VHPWR | Two priority-pair refusals; endpoint/portal search exhausted |
| PCIe3 | Kelvin, pair and craft admission; preserve existing path limits |
| EPS | Four source terminal short pairs; unadmitted interface geometry ECO |
| ATX 24-pin | Three source terminal short pairs; unadmitted interface geometry ECO |

Resume the common placement/power-access dependency work after reading the
live producer result. Do not turn the echo repair into a reason to repeat
unchanged placement waves, resize boards, move high-current buses or waive
source/interface authority.
