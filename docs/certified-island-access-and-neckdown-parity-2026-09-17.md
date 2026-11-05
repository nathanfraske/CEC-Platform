# Certified island access and endpoint-contract parity

## Admitted partial-route improvement

PCIe2 advances from **0 pipeline-counted DRC errors / 9 opens to 0 / 8**.
The independent constraint checker also removes the stranded IC-supply
finding. The adopted route adds **three tracks / 4.815 mm, no vias**. Every
pre-existing copper object's native geometry and lock state, every footprint
pose, the electrical terminal identity, protected power/pair copper and the
semantic project/custom rules are unchanged.

The selected direct addition is less invasive than the separately successful
via-relocation alternative, which is not selected. The other five boards keep
their unchanged checkpoints/holds. This is not a whole-suite routing completion
or fabrication release.

**New canonical continuation:** `build/island-access-next-inputs-20260917.json`.
Only its PCIe2 row changes. New PCB SHA256:
`89dfc287a2974b35eb4367b337207f014036c8c56ffc86d86a680c42c9a8301b`.
The archive contains a fresh hash-bound `oracle.json` with eight final-PCB
residuals; do not carry the old nine-open certificates forward as current.

## Generic causes and fixes

### A displayed endpoint is not the only attachment on its copper island

The exact-pair solver previously retained the correct two endpoints but treated
their displayed anchor positions/layers as the entire problem. A representative
inner-layer track endpoint can be difficult to reach even when another point
on that same connected island has usable surface access. Whole-net fallback
then spends time on other island combinations.

`cec_certified_island_access.py` obtains both named components from native
KiCad connectivity, including the source item itself. It enumerates a bounded
portfolio using the existing route-aware anchor ranking, not a second router.
Only those two components are eligible; same-net disconnected third islands
and same-XY copper on another unconnected layer are excluded. The default
search caps are six alternatives, 8-mm anchor displacement, 25-mm pair range
(the caller may bound a larger existing pair), and 4096 native net items.
These are search budgets, not electrical constraints or global no-path proofs.

The ordinary exact solver resolves every alternative back to live geometry
and retains its layer, clearance, width, POFV and edge guards. It divides the
remaining original worker allowance across alternatives. No existing copper
is removed or moved. Results retain the original pair, native component sizes,
candidate identities, per-pair outcomes and time budgets.

The current measured source island has 147 native items and 33 nearby anchors;
the remote island is a single IC supply pad. The successful attachment uses
another existing F.Cu endpoint, not an extra via or an unrelated net island.

### Generation and recovery disagreed about a qualified pin neck-down

The first native trial connected the supply but was correctly rejected for one
new track-width error. Its 1.175-mm narrow pin escape matched the generator's
actual elongated-land/clearance calculation, while recovery still imposed the
old width-only 0.75-mm budget. Exact-pair generation also omitted explicit
membership qualification and relied on that recovery path.

Generation now qualifies its exact new endpoint tracks, and independent
qualification/recovery share one pad-geometry locality function. The existing
1.5-mm absolute cap, fine-pad contact, unbranched topology, full-width throat
and ordinary trunk width remain mandatory. Only actual qualified members
receive the existing object-scoped rule. The current custom-rule file is
semantically identical; no board-wide width allowance was relaxed.

## Independent validation

- `build/island-attachment-suite-20260917/report.json`: first v52 experiment;
  9 -> 8 opens but 0 -> 1 new width DRC, rejected and retained as evidence.
- `build/island-attachment-contract-suite-20260917/report.json`: v53 native
  direct-add and via-move alternatives, four current-family physical reviews,
  two interface holds and historical PCIe2 control, run concurrently under a
  frozen engine. Both route alternatives pass their native composite checks;
  direct-add takes 44.546 s, including physical review.
- `build/island-candidate-independent-v2-20260917/report.json`: fresh isolated
  score, constraint, route-quality and fabrication probes on both the exact
  previous input and selected output. All non-regression terms pass, plus
  complete native copper/pose/identity and semantic-rule comparisons. The v1
  review used overly strict constraint-output equality; v2 correctly accepts
  removal of a blocker and the independently verified 9 -> 8 completion-count
  change, while requiring every other blocker detail to be unchanged/removed.
- `build/island-contract-final-tests-20260917.log`: **504 tests and eight
  subtests pass**. Tests include translated/renamed native islands, third-island
  exclusion, same-XY/different-layer separation, bounded resource refusal,
  real native alternative closure, and exact positive/negative neck-down
  boundaries with mandatory full-width throats.
- `build/island-contract-generalization-20260917.json`: declared core passes;
  broader legacy debt remains 23 physical / 380 runtime findings. Full generic
  runtime/fabrication-release claims remain false.

Raw KiCad retains the same four pre-existing USB footprint hole-clearance rows
handled by the existing pipeline policy. The independent fresh pipeline score
and fab probe both report zero counted DRC. Their policy was not changed here;
this is not a claim that the raw KiCad report has no entries.

The remaining independent constraints include incomplete routing and the
pre-existing GND netclass-feature finding. The pre-existing covered-backtrack
advisory is unchanged. Fabrication probes show no new slivers, islands, drill
aspect findings or acid traps. No new thermal solve or hardware qualification
is claimed. The immutable historical fab-review control still matches its
hash, regression and probe payloads.

## Review and continuation

New source-hashed top/bottom body-free previews were visually inspected and
both dashboard image endpoints returned HTTP 200:

`http://localhost:8090/?id=20260917-island-access-pcie2-eight-open-89dfc287a297`

Windows copies are under
`C:/Users/Admin/Documents/CEC-Board-Reviews/island-access-20260917/pcie-8pin-2port/`.
The images explicitly say **PARTIALLY ROUTED / NOT FAB READY**. The dashboard's
overall failed/release badge remains appropriate while eight opens remain.

All cohorts and tests have finished. Continue from the new eight-open manifest
and its fresh residuals; the old detector-via domain is no longer the active
target. Next route work should use a bounded additive portfolio over the
remaining certified component pairs, rather than restarting placement or
repeating the old obstructed anchor. Keep the separate Hub supply/return,
PCIe3/VHP priority and EPS/ATX coupled-interface workstreams; do not declare
held boards routed or restart their unchanged exhausted placement batches.
The EPS/ATX same-depth pitch-only studies still exceed their fixed datum spans;
there is no new physical fit authority from this slice.
