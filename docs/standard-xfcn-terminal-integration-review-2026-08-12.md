# Standard Beta XFCN terminal integration review and implementation record

**Date:** 2026-08-12  
**ECAD result:** implemented on all seven current Beta main/daughterboard
authorities in the integration contract.  
**Release result:** `PROTOTYPE_BLOCKED`; this is not a Gerber or purchase-BOM
release.

## 1. Review verdict

The proposed XFCN allocation is electrically coherent as a prototype and is a
substantial simplification over the retired blade counts. The exact catalog
parts are represented by pinned manufacturer/MPN/LCSC metadata and local source
drawings:

- XFCN `T34069`, LCSC `C481452`: M3-6H, 0.5 N·m, 40 A catalog rating,
  approximately 6.3 mm body width and 9 mm catalog height.
- XFCN `TTR32100127-0600`, LCSC `C45384691`: M3-6H, 1.0 N·m, 60 A catalog
  rating, 10 mm body width, 9 mm body height, and two 2.0 × 1.5 mm mounting
  slots on a 9 mm pitch.
- ATX control companion: Samtec `TSW-102-16-G-D-RA` 2×2 right-angle male and
  `SSQ-102-03-G-D` 2×2 vertical female. The `-16` male provides an 8.13 mm
  mating length with a 5.08 mm board tail, meeting the calculated 6.4 mm
  engagement floor without the `-12` style's 14.99 mm post/tail envelope. Both
  footprints use Samtec odd/even-by-column numbering rather than a generic
  row-major 2×2 mapping. Samtec currently marks the selected `G`-plated male
  MPN as existing-customer-only, so `S`, `L`, or `T` plating must be explicitly
  source-qualified as a pin-compatible alternate before BOM freeze if the
  exact `G` part cannot be purchased.

The catalog ratings pass the plan's initial 125% screening allocation, but they
do not qualify the complete PCB/contact/fastener assembly. The dominant risk is
mechanical and contact geometry: the T34069 source drawing does not fully
dimension the screw-axis/washer/daughterboard stack, and the TTR 3D asset is a
project-authored collision envelope rather than manufacturer CAD. Both
daughterboard bolt pads therefore remain explicitly `PROVISIONAL`.

The earlier bolted-right-angle feasibility document is retained as trade-space
history. The later XFCN handoff is the prototype authority; the TE blade design
remains the production fallback until every qualification gate passes and the
owner ratifies the architecture.

## 2. Implemented allocation

| Authority | Implemented interface |
|---|---|
| ATX main | Four T34069 terminals: post-sense `+12V`, `+5V`, `+3V3`, and `+5VSB`; two TTR ground terminals |
| ATX daughterboard | Four matching T34069 M3 bolt pads; two matching TTR M3 bolt pads; retained ATX 24-position output field; compact Samtec 2×2 control header |
| EPS main | Per cable: two T34069 post-shunt `+12V` terminals and two T34069 ground terminals |
| EPS daughterboard | Symmetric `GND / +12V / +12V / GND` T34069 M3 bolt-pad row |
| PCIe 2-port main | Per cable: one TTR post-shunt `+12V` terminal and one TTR ground terminal |
| PCIe 3-port main | Same two-terminal pattern for all three independent post-shunt channels |
| PCIe daughterboard | One TTR `+12V` bolt pad and one TTR ground bolt pad |

Every physical leg of one metal terminal uses the same schematic/PCB pin
number, preventing the terminal body from being misinterpreted as several
unconnected electrical nodes.

The earlier T34069 no-hole interpretation was wrong. Product photographs show
the supplied screw/pressure washer removed from the threaded side face; the
external daughterboard must provide an M3 clearance hole just as the TTR
daughterboard does. Both corrected provisional footprints use a 3.4 mm plated
M3 normal-clearance hole. Their pad diameter, washer keepout, screw-axis edge
datum, thread engagement, and surface-finish stack remain sample-gated.

The legacy ATX `SR1`–`SR6` pads were also retired. They were no-net, PCB-only
placeholders with no mating path, ADC channel, protection, or firmware contract
and therefore performed no sensing. Any future connector-health monitor must
be introduced as an explicit remote-sense subsystem, not anonymous DNP copper.

## 3. Reusable implementation controls

- `scripts/cec_xfcn_contract.py` is the single data authority for exact parts,
  refdes, nets, removals, placements, and qualification state.
- `scripts/splice_xfcn_terminal_integration.py` performs the schematic
  transformation from that contract.
- `scripts/cec_xfcn_place.py` materializes the physical interface, refuses
  footprint collisions or insufficient drilled-hole edge margin, applies only
  explicitly contracted compact outlines, removes copper entering a replaced
  interface envelope, adds symmetric bolt-pad stitching, and is idempotent on
  an already-integrated board. Forced route regeneration reuses compliant
  footprints and verifies generated copper against the final KiCad net table.
- `scripts/splice_usb_ingress_common.py` now recognizes generated top-level
  schematic objects at column zero as well as tab-indented objects. This fixes
  the generic surgical-splice failure that initially deleted the wrong symbol.
- `tests/test_xfcn_terminal_contract.py` prevents retired refs, wrong counts,
  wrong nets, missing pinned libraries, PCB/source drift, a return of the
  column-zero splice bug, or an evidence-free release-state change.
- `docs/standard-xfcn-terminal-qualification-status.json` is fail-closed. ECAD
  completion cannot change a physical qualification gate by itself.

The shared provisional footprints keep manufacturing notes on `F.Fab` rather
than silkscreen-over-copper. Nonfunctional custom DRC exceptions were removed;
unqualified bolt-pad copper-edge geometry remains visible as an error.

## 4. Verification results

### Schematic and contract

- KiCad error-severity ERC: **0 violations on 7/7 current authorities**.
- Contract audit: **PASS**, with release state **PROTOTYPE_BLOCKED**.
- Regression tests: **11/11 pass**, including explicit M3-hole, main-terminal
  land-pattern, exact Samtec 2×2 numbering, compact-outline, hard-DRC, and
  unconnected gates.
- A no-force physical pass reports all 7 projects `already-integrated`, proving
  the transform is idempotent.
- Affected BOMs were regenerated. Purchased terminal rows carry the exact
  XFCN manufacturer, MPN, and LCSC codes; daughterboard contact lands are
  correctly excluded from BOM/position output.

### Current PCB DRC snapshot

All-severity KiCad DRC reports are stored under
`output/xfcn-integration-20260812/drc/`. Warning counts include legacy
silkscreen/courtyard presentation findings; the error column is the release
relevant one.

| PCB | Errors | Warnings | Unconnected | Error classes |
|---|---:|---:|---:|---|
| ATX main | 7 | 164 | 232 | invalid outline 1; hole clearance 4; zone intersection 2 |
| EPS main | 10 | 375 | 197 | copper-edge 3; courtyard overlap 3; hole clearance 4 |
| PCIe 2-port main candidate | 4 | 483 | 193 | hole clearance 4 |
| PCIe 3-port main candidate | 5 | 491 | 223 | courtyard overlap 1; hole clearance 4 |
| ATX daughterboard | 0 | 20 | 0 | none |
| EPS daughterboard | 0 | 8 | 0 | none |
| PCIe daughterboard | 0 | 8 | 0 | none |

The three compact daughterboards are now **54.0 × 21.3 mm ATX**, **28.0 ×
18.5 mm EPS**, and **27.5 × 20.0 mm PCIe**. Relative to their preceding live
outlines, that is an 11.8%, 9.2%, and 11.3% area reduction respectively. All
three have zero error-severity DRC and zero unconnected items; their residual
findings are presentation-only silkscreen warnings.

The XFCN integration is not the source of the large main-board unconnected
counts: those current main PCBs remain placement/routing-incomplete baseline
authorities. This integration places and constrains the replacement interface;
it does not claim to have completed their full routers.

## 5. Release blockers and required next evidence

1. Owner ratification of XFCN as the production architecture.
2. Incoming T34069 dimensional measurements, especially lead seating,
   screw-axis, thread depth, supplied screw/pressure-washer envelope,
   board-edge datum, permissible board thickness, and contact overlap.
3. Incoming TTR32100127-0600 measurements, including thread depth, bolt
   engagement, washer/contact envelope, and true installed height.
4. A representative copper-finish/contact/fastener coupon tested at the
   documented sustained current, torque, thermal rise, millivolt drop, thermal
   cycling, retorque, and fault-pulse conditions.
5. Released M3 fastener, washer/locking method, torque, thread engagement, and
   chassis strain-support specification.
6. JLC confirmation for the exact THT/manual-weld process and copper/finish
   stack.
7. Completion of the baseline board work: a valid ATX `Edge.Cuts` outline,
   remaining main-board placement/routing, and all non-qualification DRC and
   unconnected closure.

Until these are complete, the new files are suitable for controlled prototype
fit/coupon work only. They are not suitable for production Gerbers or an
unqualified purchase release.
