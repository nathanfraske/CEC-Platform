# Standard Beta XFCN terminal integration handoff

**Date:** 2026-08-12  
**Status:** implemented as a qualification-gated Beta prototype on 2026-08-12;
production release remains blocked by sections 9 and 10.  
**Decision being handed off:** prototype the low-height XFCN terminal scheme
for the current Standard ATX, EPS, and PCIe output daughterboards while keeping
the default 4.2 mm cable connector fields and compacting each board only to a
checked component, tool-access, and drilled-hole-margin floor.

## 1. Release boundary

The original handoff deliberately stopped one step before board edits. The
2026-08-12 implementation has now crossed that ECAD boundary: exact parts,
symbols, footprints, provisional daughterboard lands, schematics, PCB
placements, and prototype BOMs are present. It has **not** crossed the release
boundary. Gerbers and purchase BOMs remain blocked until the incoming-sample
and electrical qualification gates in sections 9 and 10 pass.

The proposal supersedes the blade interface only after owner ratification and
the associated specification/manifest documentation is updated. Until then,
the TE 63969-1/63951-1 blade design remains the ratified fallback.

### Implementation record (2026-08-12)

The current sources and PCBs listed below now implement this allocation. The
machine-readable authority is `scripts/cec_xfcn_contract.py`; the idempotent
source and physical transforms are `scripts/splice_xfcn_terminal_integration.py`
and `scripts/cec_xfcn_place.py`; release evidence is fail-closed in
`docs/standard-xfcn-terminal-qualification-status.json`. Regression coverage
is in `tests/test_xfcn_terminal_contract.py`. Passing those checks proves only
that the prototype ECAD matches this plan. It does not qualify the provisional
daughterboard lands or authorize Gerbers/BOM release.

The ATX implementation also retires the six PCB-only `SR1`–`SR6` OQ-88
provision pads. They had no nets, mating path, ADC channels, or firmware
contract and therefore performed no sensing. A future connector-health monitor
must be added as a complete, reviewed remote-sense subsystem rather than as
anonymous DNP copper.

## 2. Current design authorities

The files below are the current Beta authorities in
`scripts/cec_beta_manifest.py`; historical root boards were not substituted.

| Product | Current main design | Current daughterboard |
|---|---|---|
| ATX 24-pin rev3 | `beta/atx-24pin-rev3/24pin-module.kicad_sch` and `.kicad_pcb` | `beta/output-daughterboards/atx24-out-db/atx24-out-db-board.kicad_sch` and `.kicad_pcb` |
| EPS 8-pin rev3 | `beta/eps-8pin-rev3/eps-8pin-rev3.kicad_sch` and `.kicad_pcb` | `beta/output-daughterboards/eps-out-db/eps-out-db-board.kicad_sch` and `.kicad_pcb` |
| PCIe 2-port | `beta/pcie-8pin-2port/pcie8pin-2port-module.kicad_sch` and `candidate/pcie-8pin-2port-candidate.kicad_pcb` | `beta/output-daughterboards/pcie-out-db/pcie-out-db-board.kicad_sch` and `.kicad_pcb` |
| PCIe 3-port | `beta/pcie-8pin-3port/pcie8pin-3port-module.kicad_sch` and `candidate/pcie-8pin-3port-candidate.kicad_pcb` | Same per-cable PCIe daughterboard |

The implemented compact daughterboard outlines are 54.0 × 21.3 mm ATX,
28.0 × 18.5 mm EPS, and 27.5 × 20.0 mm PCIe. These reduce area by 11.8%, 9.2%,
and 11.3% respectively from the preceding live boards. The contract does not
authorize later outline growth and fail-closes on drilled-hole edge margin and
footprint collision.

## 3. Exact parts and sourcing disposition

| Use | Manufacturer / MPN | Catalog identity | Manufacturer drawing facts | JLC disposition on 2026-08-12 |
|---|---|---|---|---|
| 40 A compact threaded-face terminal | XFCN `T34069` | LCSC/JLC `C481452`; [LCSC](https://www.lcsc.com/product-detail/C481452.html); [JLC](https://jlcpcb.com/partdetail/Xfcn-T34069/C481452) | 40 A, M3-6H, 0.5 N·m, four legs, 6.3 mm wide, 9 mm high; tin-plated H62(Y2) brass; catalog photographs show a separate supplied screw/pressure washer for the threaded side face | Extended; THT manual-weld / wave-soldering record |
| 60 A threaded right-angle terminal | XFCN `TTR32100127-0600` | LCSC/JLC `C45384691`; [LCSC](https://www.lcsc.com/product-detail/C45384691.html); [JLC](https://jlcpcb.com/partdetail/Xfcn-Ttr321001270600/C45384691) | 60 A, M3-6H, 1.0 N·m, two legs, 10 mm wide, 9 mm installed body height; tin-plated H62(Y2) brass and SPCC washer | Extended; THT manual-weld / wave-soldering record |
| ATX 2×2 right-angle male | Samtec `TSW-102-16-G-D-RA` | [Samtec exact part](https://www.samtec.com/products/tsw-102-16-g-d-ra) | 2.54 mm pitch, double row, 8.13 mm in-plane mating length (`C`) and 5.08 mm board tail (`E`); satisfies the calculated ≥6.4 mm engagement floor | Consigned/non-JLC catalog; exact `G` MPN currently existing-customer-only; qualify `S`, `L`, or `T` plating alternate if needed; first-article fit gate |
| ATX 2×2 vertical female | Samtec `SSQ-102-03-G-D` | [Samtec exact part](https://www.samtec.com/products/ssq-102-03-g-d) | 5.59 × 4.95 × 8.51 mm body; 10.01 mm `-03` tail | Consigned/non-JLC catalog; first-article fit gate |

Both exact XFCN component MPNs are sourceable through the intended LCSC/JLC
catalog. Neither is a Basic part. Samtec lists the exact 2×2 pair and compatible
plating variants, but currently flags the selected `G`-plated TSW male as
existing-customer-only. BOM freeze must therefore either confirm access to that
exact MPN or explicitly qualify a geometry-compatible `S`, `L`, or `T` variant.
Stock and price are volatile and must be refreshed at BOM freeze.

The T34069 catalog photographs show a supplied M3 screw/pressure washer, but
its exact screw length and washer/contact dimensions are not specified by the
drawing. Inventory and qualify the received hardware. The M3 daughterboard
fastener for TTR is intentionally not assigned a cosmetic retail MPN yet.
Procure a traceable M3 × 0.5 machine screw and compatible washer/locking stack
after measuring thread depth and calculating engagement. An initial TTR fit
coupon may try M3 × 6 mm, but that length is not a released BOM choice. Both
daughterboards require an M3 clearance hole through the external conductor.

## 4. Delivered ECAD package

| Deliverable | Path | Status |
|---|---|---|
| Symbols | `lib/vendor/Connector_Screw.kicad_sym` | Four reviewed one-node symbols: two terminal BOM symbols and two non-BOM daughterboard-interface symbols |
| Main-board footprints | `lib/vendor/Connector_Screw.pretty/XFCN_T34069_THT_M3_40A.kicad_mod`; `.../XFCN_TTR32100127-0600_THT_M3_60A.kicad_mod` | Usable for prototype layout; every physical leg is pad `1`; sample verification remains mandatory |
| Daughterboard lands | `lib/vendor/Connector_Screw.pretty/XFCN_T34069_Daughterboard_BoltPad_M3_PROVISIONAL.kicad_mod`; `.../XFCN_TTR32100127-0600_Daughterboard_BoltPad_M3_PROVISIONAL.kicad_mod` | Explicitly provisional; both use a 3.4 mm plated M3 normal-clearance hole; pad/washer/edge geometry remains sample-gated |
| T34069 3D | `lib/3dmodels/Connector_Screw.3dshapes/XFCN_T34069_native.step` and `.wrl` | Native EasyEDA model from C481452; footprint-aligned |
| TTR 3D | `lib/3dmodels/Connector_Screw.3dshapes/XFCN_TTR32100127-0600_envelope.step` | Reproducible drawing-derived collision envelope, not manufacturer CAD |
| Reproduction/source record | `lib/vendor-data/Connector_Screw/README.md` and `lib/3dmodels/Connector_Screw.3dshapes/source/` | Records provenance, missing native CAD, regeneration, and sample measurements |
| Integration BOM/count matrix | `lib/vendor-data/Connector_Screw/integration-bom.csv` | Exact terminal counts per current Beta module plus unresolved hardware gates |
| Local source drawings | `lib/datasheets/XFCN_T34069_C481452.pdf`; `lib/datasheets/XFCN_TTR32100127-0600_C45384691.pdf` | Manufacturer PDFs copied locally and visually verified |
| ATX control pair | `lib/vendor/Connector_PinHeader_2.54mm.pretty/Samtec_TSW-102-16-G-D-RA_2x02_P2.54mm_Horizontal.kicad_mod`; `lib/vendor/Connector_PinSocket_2.54mm.pretty/Samtec_SSQ-102-03-G-D_2x02_P2.54mm_Vertical.kicad_mod` | Exact 2×2 physical mapping; Samtec odd/even-by-column pins 1/2 and 3/4; local TSW/SSQ drawings pinned in `lib/datasheets/` |

### Project library-table additions

Add these two entries to each affected main-board and daughterboard project.
The depth shown is correct for all current Beta projects directly under
`beta/<project>` and `beta/output-daughterboards/<project>` when the latter use
one additional `..` as shown.

Main boards:

```scheme
(lib (name "cec-Connector_Screw")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/Connector_Screw.pretty")(options "")(descr "CEC reviewed XFCN high-current screw-terminal assets"))
(lib (name "cec-Connector_Screw")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/Connector_Screw.kicad_sym")(options "")(descr "CEC reviewed XFCN high-current screw-terminal symbols"))
```

Daughterboards:

```scheme
(lib (name "cec-Connector_Screw")(type "KiCad")(uri "${KIPRJMOD}/../../../lib/vendor/Connector_Screw.pretty")(options "")(descr "CEC reviewed XFCN high-current screw-terminal assets"))
(lib (name "cec-Connector_Screw")(type "KiCad")(uri "${KIPRJMOD}/../../../lib/vendor/Connector_Screw.kicad_sym")(options "")(descr "CEC reviewed XFCN high-current screw-terminal symbols"))
```

The first line belongs in `fp-lib-table`; the second belongs in
`sym-lib-table`. The footprints' 3D paths are authored for main-board depth.
If a main-side terminal footprint is ever placed inside a daughterboard
project, change only that local model path from `../../lib` to `../../../lib`.

## 5. Electrical allocation

The counts below preserve the platform's 125% connector-sizing convention.
Manufacturer ratings are screening numbers until qualification proves the
assembled terminal/PCB/bolt system.

| Board | Rail allocation | Proposed sites | Rating sum | Design target | Disposition |
|---|---|---:|---:|---:|---|
| ATX | `+12V`, `+5V`, `+3V3`, `+5VSB` | one T34069 per rail | 40 A each | 20–37.5 A per positive rail, depending on platform envelope | Meets documented per-rail targets; verify exact ATX rail envelope at schematic change |
| ATX | common `GND` | two TTR terminals in parallel | 120 A aggregate | 72.5 A simultaneous return target | Rating sum passes; no sharing credit until paths are symmetric and measured |
| EPS, each cable | post-shunt `+12V` | two T34069 in parallel | 80 A aggregate | 65 A | Passes by rating sum; enforce symmetric copper/current sharing |
| EPS, each cable | `GND` | two T34069 in parallel | 80 A aggregate | 65 A | Same |
| PCIe, each cable | post-shunt `+12V` | one TTR | 60 A | 48.75 A | Passes by rating; test at 48.75 A minimum |
| PCIe, each cable | `GND` | one TTR | 60 A | 48.75 A | Same |

Current schematic connectivity was exported with KiCad 10 before writing this
plan. The live blade mappings are: ATX one +12V, two +5V, two +3V3, one +5VSB,
four GND; EPS daughterboard three +12V and three GND; PCIe daughterboard three
`+12V` and three GND. The implementation must replace each *group* with the
allocation above; it must not perform an unsafe one-for-one footprint swap.

For EPS, the current main schematic still exposes `J_OUT1/J_OUT2` Mini-Fit Jr
headers rather than blade terminals. Replace those output-side connector nodes
with the four-terminal-per-cable pattern while leaving the shunt/sense topology
unchanged: terminal source pads connect to `/SENSEC1_LO` or `/SENSEC2_LO`, not
to the pre-shunt rail.

For PCIe, map the new positive terminals to `/SENSEC1_LO`, `/SENSEC2_LO`, and
`/SENSEC3_LO` respectively; do not collapse the post-shunt nets into a shared
+12V node. Grounds remain common.

## 6. Board-by-board implementation

### ATX 24-pin

1. Replace the ten `TB1..TB10` TE 63969-1 blade receptacles with four
   `XFCN_T34069` symbols and two `XFCN_TTR32100127-0600` symbols. Preserve
   `+5V_MAIN`, `/SENSE3V3_LO`, `/SENSE5VSB_LO`, `/SENSE12V_LO`, and `GND`
   exactly.
2. Replace daughterboard `J10..J19` with four T34069 M3 bolt-pad symbols and two
   TTR M3 bolt-pad symbols on the matching rails. Retain the 24-pin 4.2 mm
   output field and its net mapping. Replace the former 1×4 signal companion
   with the Samtec 2×2 pair: daughterboard `TSW-102-16-G-D-RA`, main-board
   `SSQ-102-03-G-D`; 1=`-12V`, 2=`PS_ON#`, 3=`PWR_OK`, 4=`GND` using Samtec
   odd/even-by-column numbering. These power terminals do not carry signals.
3. Put the two ground TTR sites at opposite ends of the ground copper fanout or
   otherwise make their main-board and daughterboard path impedances
   geometrically equal. Do not route one ground terminal through the other.
4. Package all six sites inside the implemented 54.0 × 21.3 mm outline.
   Keep the default ATX output connector field unchanged.

### EPS 8-pin

1. Per cable, use four `T34069` terminals: two tied to the cable's post-shunt
   +12V node and two tied to GND. Do not combine cables at the interface.
2. On the daughterboard, replace the three +12V and three GND blade tabs with
   two +12V and two GND T34069 M3 bolt pads. Retain the existing 2×4 4.2 mm
   output field and its standard pin mapping.
3. Pair each polarity symmetrically around its connector pin bank. Give both
   members of a parallel pair the same copper length, layer transitions, via
   pattern, and constriction geometry.
4. Fit inside the live 28.0 × 18.5 mm outline. The four terminal sites are the
   maximum allowed by this handoff.

### PCIe 2-port and 3-port

1. Per cable, replace the six blade receptacles with one positive and one
   ground `TTR32100127-0600`. Preserve a separate post-shunt positive net for
   every cable.
2. On the common PCIe daughterboard, replace `J10..J15` with one +12V and one
   GND TTR M3 bolt pad. Retain the 2×4 4.2 mm cable connector field.
3. Keep the PCIe daughterboard at or below the live 27.5 × 20 mm outline. Place
   the two M3 axes so both fasteners remain tool-accessible after the chassis
   support is installed.
4. Apply the same per-cable pattern to all two or three channels; do not share a
   terminal across cable outputs.

## 7. Copper and schematic rules

1. Every solder leg in one metal terminal is one electrical node. The supplied
   symbols expose one passive pin and the supplied main-board footprints number
   every physical leg `1`. Do not restore the raw EasyEDA separate-pin model.
2. Use solid pad-to-pour connections at the high-current terminal pads; do not
   use narrow thermal spokes. Preserve wide multi-layer current paths and
   symmetric stitching outside the washer/contact area.
3. T34069 daughterboard pads are exposed copper on both sides around a 3.4 mm
   plated M3 normal-clearance hole. The supplied screw/pressure washer passes
   through the daughterboard and threads into the terminal's external side
   face. Keep soldermask, silkscreen, labels, and vias out of the measured
   washer/contact footprint.
4. TTR daughterboard pads use the same external-bolt topology: exposed copper
   on both sides around a 3.4 mm plated M3 normal-clearance hole. The screw
   passes through the daughterboard and threads into the terminal. Keep
   soldermask, silkscreen, labels, and vias out of the washer/contact footprint.
5. Treat the mechanical joint as a conductor: the selected surface finish,
   washer stack, torque, copper thickness, and chassis constraint are part of
   the electrical implementation.
6. Do not count chassis reinforcement as electrical parallel conductance. The
   chassis prevents board bending; it does not replace the terminal or copper
   path.
7. The primary separable electrical and thermal interface is the flat plated
   terminal face directly against the exposed `F.Cu` daughterboard clamp land.
   The washer is on the opposite (`B.Cu`) face and is credited only for preload
   distribution, not as parallel current or heat conductance through the screw.
   Do not add a thermal pad, conductive elastomer, grease, carbon-filled sheet,
   or other unspecified conforming interposer. Such materials add unqualified
   bulk/contact resistance and can creep or relax clamp load. If testing shows
   that the direct land cannot meet resistance/temperature/retention limits,
   redesign around a qualified rigid plated copper contact plate, PCB coin,
   compression limiter/busbar, or purpose-designed power connector.
8. Current prototype boards declare ENIG. Do not infer from that declaration
   that the finish is qualified for a serviceable bolted power joint. Release
   requires the actual finish thickness and terminal-face plating to be recorded
   and the complete interface to pass the four-wire, thermal-cycle, handling,
   and reuse tests below.
9. The prototype contact-system BOM is therefore explicit: tin-plated XFCN
   terminal face directly against the flat ENIG daughterboard land; no thermal
   interface material, conductive grease, elastomer, loose copper foil, copper
   coin, or separate contact plate. The board properties
   `CEC_XFCN_CONTACT_INTERFACE`, `CEC_XFCN_CONTACT_INTERPOSER`, and
   `CEC_XFCN_COPPER_COIN` encode this choice and the contract audit checks the
   ENIG declaration plus two-sided soldermask exposure. A rigid plated copper
   plate, coin, or compression limiter is a redesign option only if coupon
   testing shows unacceptable resistance, temperature rise, laminate creep, or
   torque retention; it is not a default prototype component.

## 8. Mechanical and height target

The TTR drawing gives a 9 mm installed body-height envelope. T34069 is less
settled: LCSC calls it 9 mm above board, while its native 3D model registers
about 5 mm above the inferred PCB seating plane and 4 mm of lead below. Use the
catalog's 9 mm as the conservative clearance until an incoming sample resolves
the datum. The daughterboard rises from the threaded-face bolt axis, and the retained
vertical 4.2 mm output connector dominates the upper envelope. With the
daughterboard bottom edge kept close to the main PCB and the connector field
placed at the lowest legal edge datum, target a 19–20 mm maximum installed
height above the main PCB. This preserves the previously agreed compactness
goal and is materially lower than the roughly 32–34 mm blade configuration.

Do not freeze the exact Z dimension from the supplied TTR collision model or
the provisional lands. Update the 3D assembly using measured screw-axis and
board-edge datums from incoming samples, then confirm:

- no board or connector envelope exceeds 20 mm above the main PCB;
- no daughterboard outline grows;
- driver access exists for every TTR bolt and supplied T34069 bolt;
- the chassis support bears cable insertion/removal loads rather than the THT
  legs or the copper bolt pads.

## 9. Incoming-part ECAD release gate

Before prototype Gerbers, measure at least five specimens per MPN and record
min/max values. Required measurements are enumerated in
`lib/vendor-data/Connector_Screw/README.md`. At minimum:

- verify every THT slot position and lead cross-section against the footprint;
- verify installed height and orientation against the 3D asset;
- verify T34069 thread depth, supplied screw length, pressure-washer OD/contact
  envelope, M3 clearance, and screw-axis-to-daughterboard-edge datum;
- verify TTR thread depth, washer OD, M3 screw length/engagement, and the
  screw-axis-to-daughterboard-edge datum;
- rename/remove `PROVISIONAL` only after the measurements are incorporated and
  peer-reviewed.

No outside sourcing action is currently required for the two terminals. If
XFCN releases native TTR STEP CAD later, replace the envelope model only after
its footprint registration is checked.

## 10. Electrical and assembly qualification gate

Build a representative main-board/daughterboard coupon before line-wide
adoption. The user has already authorized recommendation/implementation work
without waiting for test results; this gate controls production release, not
the start of design work.

1. Test each single 40 A T34069 path at its actual ATX rail current target and
   each single 60 A TTR path at 48.75 A for PCIe.
2. Test each EPS two-terminal parallel path at 65 A aggregate. Measure branch
   current separately; reject a layout whose higher-current branch exceeds its
   40 A nameplate or whose sharing materially drifts during heat soak.
3. Test the two-terminal ATX ground path at 72.5 A aggregate with representative
   simultaneous rail loading and the same branch-current requirement.
4. Record milliohm-level end-to-end joint resistance and temperatures at the
   terminal body, THT solder region, daughterboard contact land, and adjacent
   copper before/after thermal cycling and handling. A four-wire instrument is
   appropriate for this connector-joint measurement; this does not change the
   platform's two-terminal shunt architecture.
5. Enforce the manufacturer thread-torque ceilings: 0.5 N·m T34069 and 1.0
   N·m TTR. Establish the released fastener, washer, locking method, calibrated
   tool, torque-stripe/inspection method, and service-reuse policy.
6. Run cable insertion/removal and chassis handling with the board fully
   supported. Inspect for pad lift, laminate crushing/delamination, solder
   cracking, terminal rotation, screw loosening, and resistance change.
7. Confirm the JLC order's THT assembly selection for both Extended parts.
   Upload BOM/CPL with exact LCSC codes and manually verify their orientation;
   automated matching alone is not acceptance.

Any electrical, thermal, fastener, or material failure returns the affected
board to the blade interface until the failure is corrected and requalified.

## 11. Handoff checklist

- [ ] Add `cec-Connector_Screw` to `sym-lib-table` and `fp-lib-table` for every affected project.
- [ ] Create a feature branch; do not edit archived boards.
- [ ] Implement PCIe first: it uses one TTR per polarity and is the cleanest coupon.
- [ ] Incorporate incoming TTR measurements; release its footprint, bolt pad, screw stack, and 3D registration.
- [ ] Build and qualify one PCIe main/daughterboard coupon at 48.75 A.
- [ ] Implement EPS with two T34069 per polarity per cable; incorporate incoming bolt-joint and land measurements.
- [ ] Verify measured current sharing and 65 A thermal performance.
- [ ] Implement ATX last; retain output field and all low-current signal connections.
- [ ] Verify two-ground-terminal current sharing at 72.5 A simultaneous return load.
- [ ] Confirm all three daughterboards remain within their live outlines and the assembled height is at most 20 mm.
- [ ] Run KiCad ERC/DRC, BOM/CPL export, 3D interference review, and independent schematic net-map review.
- [ ] Update ratified connector architecture, BOM, assembly work instruction, service documentation, and any blade-specific tests only after qualification passes.

## 12. Asset integrity hashes

SHA-256 values at handoff creation:

```text
aeb289f999fd47b19452f6d1e189f301dc1e5184af5c60d663a88590313a79c2  lib/datasheets/XFCN_T34069_C481452.pdf
225f003c0f0bb488b49bb96fac2477091c8f882ff6da7b9f5db3799f9145b750  lib/datasheets/XFCN_TTR32100127-0600_C45384691.pdf
aa4f71ffcf34d1804cc5858da1dc7d34e318b373103d04c371f83748f3841681  lib/3dmodels/Connector_Screw.3dshapes/XFCN_T34069_native.step
e9dabc78e4e6c393b81564cb2200ca939356ff07ceee67ed9caddaa300095776  lib/3dmodels/Connector_Screw.3dshapes/XFCN_T34069_native.wrl
04a159f7e94dda418759e83d5e3cc065a959d41f8ceea7bc18700767a780b113  lib/3dmodels/Connector_Screw.3dshapes/XFCN_TTR32100127-0600_envelope.step
3a5770b11668f4e5a11ba9ceeb4817a23f467b8507e3592f55fb6bd8f96e71bc  lib/datasheets/Samtec_TSW_TH.pdf
3609be190ef021cc260abf423296449d797dd474fe1618dcf0fec719e2a05141  lib/datasheets/Samtec_SSQ.pdf
bbcedf98797c5172b4366bcfce259b3c6654d5ad13f8233ce9c9e8adb418df3a  lib/vendor/Connector_PinHeader_2.54mm.pretty/Samtec_TSW-102-16-G-D-RA_2x02_P2.54mm_Horizontal.kicad_mod
2b14026d6df1ed9c934d919c6eeaeb9058c00326353c49fe393bbf5909b3ca6d  lib/vendor/Connector_PinSocket_2.54mm.pretty/Samtec_SSQ-102-03-G-D_2x02_P2.54mm_Vertical.kicad_mod
```

Text-library hashes will change when incoming sample measurements are applied;
the source PDFs and native T34069 model should remain pinned.
