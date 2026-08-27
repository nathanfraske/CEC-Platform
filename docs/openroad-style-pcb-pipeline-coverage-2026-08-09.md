# OpenROAD-style PCB pipeline coverage — 2026-08-09

This document distinguishes an implemented pipeline stage from a stage that is
merely described, and a passing checker from a fabbable board. The analogy to
OpenROAD is architectural: progressively more physical information is added,
each stage has an admission contract, detailed failures feed bounded repair or
placement, and final signoff is a conjunction rather than a weighted score.

## Executable flow

~~~mermaid
flowchart TD
  A[Hierarchical schematic, ERC, BOM and source data] --> B[Constraint IR and board/fab policy]
  B --> C[Outline, mechanical, connector and access floorplan]
  C --> D[Critical macro and functional-cell placement]
  D --> E[Pad-aware passive and decoupler placement]
  E --> F[Placement legality, pin access and future-congestion preflight]
  F --> G[Precision pairs, Kelvin and declared critical controls]
  G --> H[Local bypass GND entries and POFV reservation]
  H --> I[Routed power objects and immutable reservations]
  I --> J[Global congestion forecast and hierarchical route tiers]
  J --> K[Residual detailed routing]
  K --> L[Certificate-driven bounded repair]
  L --> M[Local bypass supply finish, GND fanout, zone refill and craft finish]
  M --> N[DRC, connectivity, topology, SI, thermal and DFM signoff]
  N --> O[Fab outputs plus human review]
  F -- placement counterexample --> D
  G -- pair or launch refusal --> D
  H -- no legal return --> E
  K -- endpoint/blocker certificate --> J
  L -- no monotonic repair --> D
  N -- exact blocker ledger --> D
~~~

Every backward edge is evidence-driven and bounded. A failing route never
becomes acceptable by lowering a clearance, ignoring a ratline, synthesizing
thermal-only copper, or accepting a topology advisory as connectivity.

## Coverage matrix

| Professional-flow function | Repository implementation | Status | Remaining closure work |
|---|---|---:|---|
| Hierarchical design import and electrical source of truth | beta hierarchical schematics, board policy, electrical audit, BOM and corpus checks | Implemented | Make every beta family use the same generated manifest and stale-revision exclusion contract |
| Constraint representation | cec_constraint_ir, cec_board_policy, cec_constraints, netclasses, fab profiles | Implemented | Broaden rule coverage and add schema migration/version compatibility tests |
| Floorplan and mechanical I/O | fixed outline placement, connector/access constraints, mezzanine and THT backside checks | Implemented | Enclosure-level collision model and automated cable insertion envelope proof |
| Global and detailed placement | strategy search, legalization, functional affinity, pad-aware selected-device placement | Implemented | Scale proof from Hub-sized packages through high-pin-count BGA escape planning |
| Decoupler placement and local power cell | one-to-one device/pin ownership, actual supply-pad path search, cap/owner-ground proximity ranking | Implemented in this slice | Calibrate per-device loop limits from each datasheet where it gives a stricter requirement |
| Pin access and array escape | route preflight, POFV-aware pin access, array ring/quadrant planning | Partial | The array plan is analyzed but is not yet a production BGA fanout generator |
| Critical routing first | precision pair/Kelvin route, declared control tier, routed-power ordering | Implemented | Expand explicit critical declarations and prove every critical class on more than one board family |
| Pair transition and return physics | coupled route, matched signal transitions, adjacent GND-return synthesis and pair admission | Implemented in this slice | Add field-solver confirmation for the final connector/package discontinuities |
| Local bypass ground priority | pre-route cap and IC GND via-in-pad/dogbone reservation against exact JLC profile | Implemented in this slice | Feed reserved barrel columns into every external-router interchange path |
| Global route forecasting | multiresolution future congestion, corridor heatmaps, hierarchical tiers | Implemented for ranking | A complete global-route guide is not yet handed to every detailed-router search state |
| Detailed routing | Freerouting fork, staged high-effort tiers, local completion and coordinate router | Implemented | Hub remains open; dense enterprise/BGA routability is not proven |
| Negotiation and repair | refusal certificates, bounded target-first copper surgery, transactional fab repair | Partial | Placement feedback still needs a generalized blocker-to-move compiler for all final DRC types |
| Route topology craft | stub/double-back/angle analyzer, transactional chamfer and teardrop audit | Implemented | Tune advisory thresholds against a larger professionally reviewed board corpus |
| DRC/connectivity signoff | same-run KiCad raw violation evidence, zero-unconnected release gate, pair/Kelvin topology | Implemented | Add independent electrical netlist-to-PCB equivalence beyond the present circuit checks |
| Per-blocker fail stack | stable blocker IDs, UUID-attributed/associated stage chains, final issue dashboard | Implemented for new runs | Historic boards have no creation ledger; unattributed history stays explicitly unknown |
| SI and return-path signoff | impedance, pair physical quality, layer-reference policy, return-via checks | Partial | No general 3D discontinuity or full-channel simulation gate yet |
| Power integrity and thermal signoff | declared-current 2.5D solve, injection completeness, current-density rules | Partial | No general DC IR-drop/PDN optimizer; incomplete injection remains a hard Hub blocker |
| DFM and fab handoff | named JLC profiles, POFV qualification, fab checks, fab script and dashboard | Partial | The fab script is not yet the sole release oracle; panel, assembly and output-package validation need one signed manifest |

## Local bypass-cell contract

For every selected powered-device requirement, a distinct value-compatible
capacitor is assigned to one actual supply pin. Placement minimizes the guarded
explicit supply path plus the distance from the capacitor GND pad to the nearest
owner GND pin. The current policy requires:

- assignment within the device-specific or project supply-pin limit;
- capacitor GND pad within 2.5 mm of the nearest owner GND pin;
- an explicit local supply path no longer than max(direct + 0.35 mm, 1.35 times direct);
- a connected GND via within 1.5 mm of both the capacitor GND pad and owner GND pin;
- filled/capped via-in-pad only when the board declares an approved POFV profile and the exact land, drill, annular ring, net and through-stack collision checks pass;
- the shortest legal dogbone when POFV cannot be proven;
- no DRC, connectivity, Kelvin or pair regression.

Ground entries run before global routing. The final supply/cell finish runs after
detailed routing and is re-measured from the deliverable board. A close-looking
capacitor with a long copper detour therefore cannot pass.

## Blocker provenance contract

The final KiCad DRC and connectivity rows used by cec_score are preserved in the
same metric object; the provenance layer does not rerun DRC against a later board
state. Each row receives a stable blocker ID and retains exact UUIDs and loci.

- Exact UUID overlap with a stage event is attributed.
- Shared net or reference only is associated and never promoted to known origin.
- Every detailed-route completion refusal resolves pad endpoints to final pad UUIDs.
- Non-DRC gates such as bypass-cell admission, rail refusal and incomplete current injection become observed blockers with their evidence payload.
- full_fail_stack is true only when every blocking row, excluding advisories, has an attributed origin.
- Old artifacts without stage ownership remain origin_unattributed instead of receiving an invented explanation.

The dashboard accepts an oracle/wave provenance JSON beside an archived board or
through the provenance option and preserves these chains in blockers.json.

## Current Hub closure sequence

The last polished Hub artifact before this slice had one structural clearance,
20 unconnected items, three topology advisories, and incomplete current
injection. A new audit additionally finds 12 of 12 selected bypass cells failing
the complete-loop contract; the previous placement-only gate did not measure
the final copper path or both ground entries.

The next valid Hub run must therefore proceed in this order:

1. Generate a placement that clears the new supply/GND proximity admission.
2. Reserve all cap and IC ground returns before residual routing.
3. Run critical pairs, controls, routed power and residual route with those objects immutable.
4. Use completion certificates to identify the exact blocker stack for every remaining open.
5. Finish local supply cells, repair only monotonic candidates, refill, and rerun the complete conjunction.
6. Run thermal only after the other release terms are clean, with every requested current net injected.
7. Archive the exact routed artifact with its oracle provenance and fab manifest.

A board is fabbable only when the release conjunction is true. The existence of
all boxes in the architecture does not imply the Hub has completed them.
