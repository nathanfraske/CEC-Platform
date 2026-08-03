# NEXT AGENT HANDOFF: REMOVE WHEN DONE

> Current as of 2026-08-03. This remains temporary because the primary boards
> do not yet pass the complete route/fabrication gate. Delete it only under the
> completion rule at the end of this file.

## Remote and product scope

- Repository: `nathanfraske/CEC-Platform`
- Branch: `agent/pcb-pipeline-audit-repairs-20260801`
- Use the branch tip; fixed commit hashes in the earlier handoff were stale.
- The current BETA set is exactly the ten entries in
  `scripts/cec_beta_manifest.py`.
- There is one EPS product: `beta/eps-8pin-rev3`. `eps-8pin` is archived
  lineage, not a product variant and not a current audit input.
- `tmp/` and `output/` are local diagnostic/render outputs and are not branch
  source unless deliberately promoted.

## Read these first

1. `docs/pcb-pipeline-design-principles-audit-2026-08-02.md`
2. `docs/beta-power-regulator-selection-2026-08-02.md`
3. `docs/mezz-structural-segments-2026-07-22.md`
4. `docs/atx-hub-can-freeze-assessment-2026-08-03.md`
5. `beta/atx-24pin-rev3/README.md`
6. `beta/hub-standard-rev2/README.md`

## Current owner decisions and implemented topology

- Current ATX rev3 and Hub rev2 are functional hierarchies. Their earlier flat
  source captures live only under `old-revisions/beta/` and cannot be
  rediscovered as current boards.
- ATX rev3 uses a TLV75533 WSON direct 3.3 V LDO. Its reviewed worst-case load
  is 204.838 mA including 20% margin against 500 mA capacity.
- Hub rev2 uses the TLV62569 buck directly for 3.3 V. Its reviewed worst-case
  load is 195.654 mA against the selected inductor's conservative 1.76 A
  thermal limit. A post-buck LDO is not required.
- Hub shutdown watches the final live `+5VSB` before the reservoir diode, not
  regulator dropout. The bounded paper result is 13.167 ms hold-up against a
  10 ms durable-commit budget, leaving 3.167 ms. OQ-56 remains a bench gate.
- ATX TPS2121 OVP uses 43.2k/10k dividers: 5.639 V nominal and
  5.287..5.948 V bounded.
- The direct ATX RJ-45 is obsolete and removed. CAN remains on the segmented
  mezzanine pending system-level proof of a CAN-free FREEZE transport; the
  assessment is informational and made no electrical change.
- The reflected dead-bug stack is the physical contract. ATX F.Cu faces Hub
  F.Cu, ATX 24-pin input is below the Hub outline, the daughterboard/output row
  is above it, and the Hub's four RJ-45 mouths are assembly-right after mating.
- The stack uses exact Samtec pairs: ATX `TSW-10x-17-G-D` long-post headers and
  Hub `SSQ-10x-03-G-D` sockets in unique 2x3, 2x4, and 2x2 segments. One fitted
  M2.5 ground lug uses an 18 mm Harwin `R25-1001802` standoff, leaving 4 mm
  nominal clearance over the approximately 14 mm RJ-45 bodies.
- The shared J6C/H1 row is at y=-25 mm in the common mating frame. Both sides
  pass the segment/mount geometry contract; ATX lays all four forced rails.
- Hub has six reverse-mount LEDs: `DL1..DL5,DL7`. DL6 is retired and bypassed
  in the chain. C29..C34 are one local 100 nF bypass per retained LED. Each
  reverse-LED footprint encodes the shine-through aperture and 0.8 mm internal
  clearance in its courtyard.
- Hub logo remains on B.Cu. `SW_RESET` and `SW_BOOT` are F.Cu-only at the
  accessible right edge; there is no reason to pay for double-sided assembly
  for these two debug controls.

## Current electrical release state

The manifest-only audit currently reports 21 blockers, 19 warnings, and 28
information findings. ATX rev3 and Hub rev2 have zero electrical blockers.
Remaining blockers are deliberately not weakened:

- 12VHPWR: one TPS2121 OVP bound exceeds the downstream regulator's 6.0 V
  absolute maximum.
- EPS rev3: legacy Schottky USB OR ingress, unapproved LP5907 capacitor
  network, and no reviewed 3.3 V load budget.
- ARGB: nine blockers covering bypass/regulator qualification, the unresolved
  SATA connector, and NTC/PPTC/PMOS 7 A margin.
- Each PCIe board: four blockers covering LP5907 qualification, TPS2121 OVP,
  and missing local U4 IN1 bypass.
- The output daughterboards have no electrical-audit findings but still need
  mating, load, and first-article proof.

## Current physical evidence

No primary BETA PCB is fabrication-ready.

- Hub placement R7 is 86x74 mm with zero placement residual, pad-boundary,
  courtyard, and courtyard-to-cutout findings. Buttons are on F.Cu and all six
  LED bypass macros are present.
- A fresh Hub route exercise still leaves 38 unconnected items. The route has
  90 structural DRC findings; independent fabrication analysis has 34 DRC
  findings and 13 acid-trap candidates. CAN skew is 5.0 mm against the 4.0 mm
  gate and thermal injection is incomplete on 9/12 requested rails. It is a
  diagnostic route, not a current release candidate.
- ATX placement R4 is 86x95 mm. All twelve placement variants had zero
  residual and all four forced rails lay. Signal routing plateau-killed at
  218/186; no completed route exists and the placement artifact has 310
  unconnected items.
- On the returned partial/existing geometry, the profile width/via checks found
  no sub-profile track width, via land/drill, annular, type, or aspect issue.
  This proves the geometry checkers execute; it does not clear missing copper.
- The checked-in Hub routed candidate is stale after the sixth LED bypass was
  added. Keep its diagnostic route scores, but never present it as current
  schematic evidence. The clean R7 board is placement evidence only.

## Dashboard and visual review

- Use one dashboard instance at `http://localhost:8090`; kill the prior process
  before restarting `scripts/cec_dashboard.py`.
- The activity feed contains the current Hub and ATX placement renders. Their
  names include `placement` so they are not confused with route signoff.
- Current hierarchical PDFs are generated under `output/pdf/` and model-free
  board renders under `output/review/`.

## Recommended next sequence

1. Close the 21 remaining electrical blockers in their authoritative schematic
   generators; rerun the manifest audit and error-level ERC.
2. Regenerate exact-schematic placement candidates. Do not inherit parts or
   net maps from stale candidate boards.
3. Improve Hub/ATX legal power corridors and signal routing without increasing
   the board outlines merely to accommodate a weak placer/router.
4. Require, in order: exact freshness, placement/orientation/cutout gates,
   strict pours, complete route, zero error-level DRC and unconnected items,
   pair/reference checks, per-segment width and via checks, laid-copper
   connectivity, electrothermal/FEM, and fabrication audit.
5. Perform first-article electrical, hold-up, load, thermal, USB/CAN,
   connector-mating, stack-clearance, ground-bond, peel, and shake tests.

## Completion rule

Delete this handoff only after:

- the remaining electrical selections and owner decisions are captured in
  permanent design records;
- regenerated candidates are exact against current schematics;
- every primary board passes the complete aggregate physical release gate, or
  each remaining failure is an explicit owner deferral in a permanent record;
- required first-article obligations are transferred to permanent issue/test
  records; and
- the final remote branch contains the replacement evidence.
