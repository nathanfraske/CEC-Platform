# Preserve neighbouring pin exits while constructing local returns

The previous dogbone search selected the first legal site in a fixed angular
order. A site can satisfy present copper clearance yet consume space needed by
an adjacent unrouted pin. The generic return builder now orders the **same
bounded site domain** by loss of existing, exact-clear neighbouring pin exits.
It still prefers qualified pad-centred POFV and existing immediate returns.

`cec_return_escape` samples short and long octilinear rays on up to 32 nearby
foreign SMD ports, using their own native netclass dimensions and the existing
exact collision/edge guards. Single-terminal nets and through-hole pads do not
claim fictional surface escape demand. Candidate return stubs and through-via
lands are ranked by newly stranded sampled ports, affected ports and lost rays.
Ties retain the original radius/angle order. Full-class return width is still
tried before a qualified pad-limited neckdown. Every selected seat still passes
all original copper, edge, hole, same-net pad, pair-overlap and endpoint gates.

This is a proposal heuristic, **not** a proof of route completion, permission to
change protected copper, or a clearance/via-size relaxation. Samples and omitted
ports are reported explicitly. No product, reference designator or absolute
board coordinate controls the implementation.

## Completed validation

- `build/return-escape-final-tests-v2-20260916.log`: **166 passed** in 14.42 s,
  one existing KiCad SWIG deprecation warning. Synthetic translated/rotated
  cases, loaded-native geometry, exact-refusal controls, transaction rollback,
  generalization and routed-incumbent protection are included.
- The native synthetic case demonstrates strictly lower escape loss while
  retaining the same 0.6/0.3 mm via and 0.4 mm return width. A forced native via
  refusal still rejects all ranked proposals without leaving copper behind.
- `build/return-escape-replay-v2-20260916/report.json`: concurrent physical A/B
  checks on four applicable current families and the historical PCIe2 control.
  The six source/hierarchy identities remain immutable. EPS/ATX are explicitly
  interface-held, not counted as successfully routed.

## Whole-cell causal counterfactual

The earlier PCIe2 certificate named a generated regulator GND return near a
soft-start pin. A fresh disposable diagnostic bound the complete six-item cell
to the producer's journal-verified board/oracle, unchanged current geometry,
owner/cap pad contracts and all 11 direct external native copper/pad/filled-zone
contacts. No producer sibling was found to reuse the generated identities.
This is diagnostic evidence only, not a production unlock receipt.

`build/local-cell-boundary-probe-v2-20260916/report.json` rebuilt the whole cell
under original and escape-aware ordering. Both retained all boundary ports and
all unrelated copper geometry, both scored **0 DRC / 9 opens**, and neither
closed the soft-start net. V1 failed on the diagnostic's assignment dictionary
iteration before any trial mutation; its incomplete output is not validation.

`build/local-cell-boundary-probe-v3-20260916/report.json` tried the soft-start
route *before* rebuilding that whole cell. It still refused before any return
was regenerated. The short cell is therefore not the sole causal obstruction:
the neighbouring current-limit resistor/pin/track and reserved power geometry
also obstruct the sampled domain. Do not integrate isolated via deletion,
arbitrary shrinkage or repeated cell-order retries as a claimed repair.

The short/long ray refinement was motivated by this counterfactual: one long
blocked ray must not erase a shorter legal exit that could turn. No variant of
this local reconstruction has been promoted; all canonical boards are retained.

## Full-pass follow-up

Launcher: `tmp/return_escape_suite_20260916.py`.
Campaign: `build/return-escape-suite-20260916`, six jobs, four workers per board,
16 trials, 600 s priority and 1,200 s job bounds, 16 GiB free-space floor.
Results and immutable body-free previews are published as jobs finish. Consult
the continuation ledger and live `suite.json` for completion, not this launch
description. No shared engine edits while this campaign is running.

The campaign is now complete (12:09:34Z–12:26:26Z). Independent journal/native
verification is `build/return-escape-suite-qualified-20260916.json`. **No closure
gain:** all four applicable outputs retain the exact canonical board bytes;
EPS/ATX stop at their fixed interface conflicts. PCIe2 independently remains
0 DRC / 9 opens, 747 tracks / 386 vias / 1,654.3125 mm, with protected copper,
qualified pairs and local cells passing. Real route selection correctly retains
the incumbent; no candidate was promoted. All six previews are published and
visually reviewed; retain the current input plan and do not repeat this cohort.
