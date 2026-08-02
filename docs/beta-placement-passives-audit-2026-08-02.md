# BETA placement, passive, topology, and pipeline audit

Date: 2026-08-02

## Result

The audit found and repaired real failures in the SPICE launcher, TPS2121
topology model, candidate freshness check, part metadata normalization,
six-layer route policy, POFV pickup synthesis, and slab-pour rebuild path.
Every one of the 11 BETA root schematics now passes a fresh error-level ERC.
Every one of the 11 bounded DC topology decks runs successfully with the
console ngspice executable.

No primary BETA PCB is ready for fabrication. The current electrical audit has
66 blockers and 38 warnings. The 15 BETA PCB files contain 357 error-severity
DRC violations and 1,374 unconnected items. All six routed or partially routed
primary candidates are stale against their current schematics. The three
output daughterboards are the only DRC-clean PCB files, but one still has an
unresolved connector selection.

The Hub is closed for now at the schematic, error-level ERC, and bounded DC
topology boundary. Its placement remains open for the planned redesign. L2 is
correctly DNP and excluded from the BOM. No inductance selection is required.

All ESP32 devices in the BETA family operate with wireless functions disabled.
There is no wireless-enabled BETA variant. The LP5907 review therefore does not
use wireless transmit-current comparisons. It still requires a complete
worst-case 3.3 V budget for the wired firmware mode and every fitted load before
the 250 mA regulator can be accepted.

## Evidence boundary

This was a source, CAD, and software audit. It included:

- 11 authoritative BETA root schematics and their generated BOM state
- 15 BETA PCB files, including six current candidate directories
- automatic placement, strict slab pours, pickups, DSN export, Freerouting,
  SES import, and route acceptance
- six-layer stackup, legal-layer, via, POFV, and mezzanine rules
- steady-state field electrical and thermal integration
- bounded DC topology SPICE and its Windows process launcher
- schematic mutation rollback and connectivity gates
- current placement, routing, pour, and design-guideline documents
- device-specific decoupling, protection, passive selection, and BOM metadata

No board was fabricated or bench-tested. The SPICE scope is not a transient,
fault-energy, analog-accuracy, signal-integrity, firmware, or thermal signoff.
The field solver is uncalibrated. A clean software result does not prove mating
fit, contact resistance, current capacity, component temperature, EMC, or
service life.

## BETA electrical and passive census

The audit parses the actual hierarchical KiCad projects, exports current
netlists, builds one inventory record per fitted part, and checks topology and
selection against device-specific rules. Candidate copies are excluded from
the schematic census.

| Board | Fitted components | Blockers | Warnings |
| --- | ---: | ---: | ---: |
| 12VHPWR Standard | 102 | 4 | 5 |
| ARGB Standard | 81 | 9 | 3 |
| ATX 24-pin rev3 | 123 | 15 | 12 |
| EPS 8-pin | 73 | 4 | 4 |
| EPS 8-pin rev3 | 46 | 3 | 2 |
| Hub Standard rev2 | 115 | 19 | 3 |
| ATX output daughterboard | 12 | 1 | 1 |
| EPS output daughterboard | 7 | 0 | 0 |
| PCIe output daughterboard | 7 | 0 | 0 |
| PCIe 2-port | 77 | 4 | 4 |
| PCIe 3-port | 91 | 4 | 4 |
| **Total** | **714** | **66** | **38** |

The blockers are not generic lint. They identify the following design inputs
or topology defects:

| Finding class | Count | Meaning |
| --- | ---: | --- |
| LP5907 capacitor network unvalidated | 8 | Every ESP32 board has nominal output-node capacitance above the documented 10 uF application range, input capacitance below output capacitance for fast-load guidance, or both. |
| LP5907 load headroom unproven | 8 | No reviewed worst-case wired-mode 3.3 V budget proves the controller plus sensing, CAN, logic, and housekeeping load remains below 250 mA with approved margin. |
| TPS2121 bypass node missing or unverified | 11 | One or more IN1, IN2, or OUT nodes lacks a selected local X5R or X7R rail-to-ground capacitor. |
| TPS2121 protection threshold | 9 | Eight populated dividers can cross above the LP5907 6.0 V absolute maximum at specified extremes. One ATX stage has OV1 tied to ground. |
| Pour-current source conflict | 8 | ATX and Hub board specifications disagree with their thermal configurations. The pipeline now refuses to pick a value. |
| Generic or unresolved connector | 12 | Eight individual connector placeholders and three unresolved mezzanine pairs lack orderable mating selections. The ATX output daughterboard has one unresolved connector. |
| ARGB input protection and power path | 5 | The SATA connector is unselected, the 7 A NTC has no current margin, the PPTC derates below 7 A above 20 C, the PMOS lacks guaranteed 5 V gate-drive resistance, and U6 lacks its required bypass. |
| Critical capacitor selection | 2 | ATX LP5907 stability capacitors C1 and C14 lack exact verified selections. |
| Legacy USB source OR | 1 | EPS rev3 still uses the superseded direct Schottky USB OR topology. |
| Missing footprint or required BOM field | 2 | ARGB J1 has no footprint and ATX J3 lacks an MPN. |

Thirty-eight warnings cover effective MLCC capacitance evidence, ESP reference
bulk-capacitance differences, fitted passives without exact order codes, DNP
filtering, and incomplete connector metadata. They remain visible because a
nominal capacitance or same-net connection is not proof of a usable decoupler.

## Decoupling and passive placement rules

The earlier universal instruction to place a 100 nF capacitor near every IC was
not sufficient. The current audit and design sheet now apply rules by device and
supply pin:

| Device family | Schematic requirement | Placement requirement |
| --- | --- | --- |
| LP5907 | At least 1 uF input. Output must be 1 uF to 10 uF, X5R or X7R, within the allowed ESR and effective-capacitance range. Fast-load guidance requires input capacitance at least equal to total output-node capacitance. | Input capacitor at the input and ground pins within the documented 1 cm limit. Output capacitor uses the shortest practical output-return loop. The complete node, not one capacitor, must pass the regulator stability review. |
| ESP32 controller modules | The Espressif peripheral references use 22 uF plus 100 nF at the module supply. That network currently conflicts with the LP5907 output-capacitance limit and must not be copied blindly. | Local supply and return loop at the module pins. Qualification uses the wired firmware load budget. |
| INA238, INA181, INA180, INA240 | One distinct 100 nF supply bypass per required supply. Sense input filters remain matched and use the device-specific topology. | Bypass at the supply pin with a direct return. Kelvin taps leave the shunt terminal copper and do not carry force current. |
| TJA1051 | Local 100 nF supply bypass. Optional bulk is determined by the rail transient design, not by a universal count. | Bypass beside the supply and ground pins. CAN routing remains referenced to continuous ground. |
| SN74AHCT244, SN74AHCT1G08, SN74LVC1G17 | One distinct 100 nF bypass per device supply. | Capacitor next to the supplied pin or pin group with a short ground return. ARGB U6 currently fails this rule. |
| TLV7011 and TPS3839 | Apply the datasheet-conditioned 100 nF local bypass rule when the rail impedance and transient environment require it. | Place at the device supply and ground loop, not elsewhere on the rail. |
| TPS2121 | Each IN1, IN2, and OUT node needs close selected X5R or X7R bypassing. No universal capacitance value was invented. | Capacitors must be local to the associated node and ground path. The PCB proximity gate follows schematic selection. |
| REF3030 | Local 100 nF is present in the reviewed design, with additional rail bulk. The revised reference documentation has inconsistent minimum-output-capacitance wording, so the network remains a review item. | Keep input, output, and ground loops local. Do not select a new value without resolving the source conflict. |

The schematic audit can prove one-to-one nominal bypass coverage. It cannot
prove placement distance on a stale PCB. Seven controller boards have complete
nominal 100 nF device coverage. ARGB fails because U6 has no distinct bypass.
Every primary candidate fails freshness, so local placement compliance remains
unproven until each PCB is synchronized and measured.

## Part-selection repairs

The audit corrected selection records only where the manufacturer and orderable
part could be verified:

- Hub C23 now identifies Samsung CL10A106MA8NRNC, 10 uF, 25 V, X5R, 0603,
  LCSC C96446.
- C15849 records now identify Samsung CL10A105KB8NNNC, 1 uF, 50 V, X5R,
  0603 on EPS, EPS rev3, and PCIe boards.
- ATX C50 is 0603 in the schematic, BOM, and generator. Its checked-in PCB
  candidate still has the old footprint and is therefore stale.
- ATX R_BYP_L1 now identifies Uniroyal 0402WGF0000TCE, LCSC C17168.
- ATX D5 now identifies UMW as the manufacturer for LCSC C545549.
- Cross-board LCSC consistency is now a hard audit gate. One order code cannot
  silently describe different values, packages, or MPNs on different boards.

No unresolved passive or protection value was guessed. Exact connector parts,
OVP divider changes, regulator changes, and current bases remain owner inputs.

## Topology and SPICE

The Windows resolver previously selected `ngspice.exe`, which opened the GUI
and repeatedly displayed parse failures. It now accepts only a console binary
and launches without a window. The resolved executable is:

`C:\Users\Admin\AppData\Local\CEC-Tools\ngspice-46\Spice64\bin\ngspice_con.exe`

The central resolver also rejects a Windows `CEC_NGSPICE` override whose
basename is `ngspice.exe`. An accidental environment override can no longer
restore the GUI executable.

The harness also now finds the root schematic, assigns unique SPICE element
names, rejects empty output and nonzero exits, and deletes temporary decks.
The TPS2121 abstraction is directional rather than a bidirectional resistor, so
the bounded DC check can detect reverse-feed topology instead of creating it.

All 11 BETA bounded DC decks pass. The probe list includes every external source
rail. The result is recorded as `dc_signoff=true` and
`functional_signoff=false`. That distinction is deliberate.

For the Hub, the exported current netlist proves U5, U7, and U11 CP2 pin 3 are
grounded and proves fixed priority `MAIN_5V > 5VSB > USB > KVM`. L2 is DNP,
`in_bom=no`, and is not required for this topology.

The same CP2 pin correction was applied to the non-BETA Enterprise Hub generator
and cascade sheet. Its generated root verifies 251 components and 285 nets.

## Candidate freshness and physical status

Freshness now compares reference, value, footprint item, assembly state, and the
numbered-pad net map. File timestamps and reference-only checks are not enough.

| Candidate | Exact signatures | Current mismatch |
| --- | ---: | --- |
| 12VHPWR | 101/102 | FL1 is missing from the PCB. |
| ATX 24-pin | 122/123 | C50 footprint differs. The intake gate also reports the schematic as newer. |
| EPS 8-pin | 70/73 | FL1 and R19 are missing; U1 pad nets differ. |
| Hub rev2 | 112/115 | U5, U7, and U11 pad nets differ. |
| PCIe 2-port | 71/74 | FL1 and R19 are missing; U1 pad nets differ. |
| PCIe 3-port | 85/88 | FL1 and R19 are missing; U1 pad nets differ. |

Fresh KiCad 10.0.4 DRC with all severities, all track errors, and zone refill
produced this census:

| PCB file | Error violations | Unconnected items |
| --- | ---: | ---: |
| 12VHPWR primary | 74 | 15 |
| 12VHPWR candidate | 11 | 47 |
| ATX primary | 7 | 235 |
| ATX candidate | 208 | 117 |
| EPS candidate | 6 | 14 |
| EPS primary | 6 | 193 |
| EPS rev3 primary | 10 | 158 |
| Hub candidate | 5 | 16 |
| ATX output daughterboard | 0 | 0 |
| EPS output daughterboard | 0 | 0 |
| PCIe output daughterboard | 0 | 0 |
| PCIe 2-port candidate | 13 | 9 |
| PCIe 2-port primary | 6 | 154 |
| PCIe 3-port candidate | 5 | 231 |
| PCIe 3-port primary | 6 | 185 |
| **Total** | **357** | **1,374** |

The DRC-clean daughterboards still need connector selection, mating fit,
first-article electrical checks, and load validation. DRC cleanliness alone is
not functional qualification.

## Six-layer route and via proof

Two pipeline profiles now carry the owner-selected roles:

| Board class | F.Cu | In1.Cu | In2.Cu | In3.Cu | In4.Cu | B.Cu |
| --- | --- | --- | --- | --- | --- | --- |
| High-current modules and ATX | Signal and power, 0.0700 mm | GND, 0.0152 mm | Signal, 0.0152 mm | Power, 0.0152 mm | GND, 0.0152 mm | Signal and power, 0.0700 mm |
| Hub | Signal, 0.0350 mm | GND, 0.0152 mm | Signal, 0.0152 mm | Power, 0.0152 mm | GND, 0.0152 mm | Signal, 0.0350 mm |

The ordinary-trace legal layers are F.Cu, In2.Cu, In3.Cu, and B.Cu. In1.Cu and
In4.Cu are exported as planes. A real Java Freerouting round trip placed a
forced `/SIG` trace on In3.Cu and imported it with zero unconnected items. This
proves layer carriage through DSN, router, SES, and KiCad import. It does not
prove that a current BETA placement is routable.

At equal resistance and current, the exact modelled 0.0152 mm inner copper
requires 2.289473684 times the width of a 0.0348 mm conductor. The field model
uses the exact layer thickness rather than calling it nominal 0.5 oz or 1 oz.

Only plated through vias are approved. Same-net via-in-pad is legal only under
the declared POFV profile with the complete via land inside the SMD pad. Blind,
buried, and microvias remain disabled. Non-through-board vias could reduce escape
congestion, but they are unnecessary for the proven legal-layer route and would
add a manufacturing process not covered by the selected free POFV offer. No cost
claim is made without a quote.

The ATX and Hub candidates carry six-layer definitions. The checked-in
12VHPWR, EPS, and PCIe candidates remain four-layer files. Their pipeline
parameters are migrated, but their physical candidates are not.

## Pour pipeline

The repaired slab path now:

- derives board identity from the loaded PCB filename
- records whether current came from the thermal configuration or board spec
- refuses conflicting current sources
- uses the current Hub ask contract rather than stale candidate zones
- removes inherited slab zones before rebuilding
- creates same-net POFV pickups where the fabrication profile and pad geometry
  permit them
- falls back to a guarded adjacent via and stub only when collision checks pass
- refuses missing anchors, overlap, missing current, and minimum-width failure

On a ripped Hub candidate, pickup synthesis created 40 pickups: 28 POFV and 12
guarded stub vias. It removed eight stale zones. Strict allocation then stopped
on real placement problems. `+5VSB`, `+5V_HOLD`, `/5VSB_RAW`, `/MAIN_5V_RAW`,
and `/VCC_P3` had minimum-width failures. `/PSU_5V` and `/PSU_5V_KVM` had no
usable inner anchor with the current placement and approved via geometry.

The ATX diagnostic obtained `+3V3` current from the board specification and the
other rails from its thermal configuration. `+3V3` and `+5VSB` failed minimum
width. The current-source audit also found the 5 A versus 0.5 A `+5VSB` conflict
and the 25 A versus 20 A `+5V_MAIN` conflict.

These failures close the software bug without pretending to close the board.
The next Hub and ATX placement pass must create legal anchors and corridors. The
pipeline must not reduce a current or a width merely to make the pour succeed.

## Field solver results

The Hub field probe is invalid as a thermal assurance result. Ten configured
power nets were dropped because their source and sink landed on disconnected
copper islands. Its apparent maximum rise of 0.536 C reflects missing current,
not a cool design.

The 12VHPWR design-basis run used 0.0152 mm inner copper, 60 C ambient, six
9.2 A channels, and 55.2 A ground return. It reached 111.0 C, a 51.0 C rise,
and 9.061 W Joule loss. It produced 12 blocking current-density or conductor
temperature flags. The solve is uncalibrated, so it is a rejection signal, not
a prediction of first-article temperature.

## Placement and design-document audit

The current authority is now explicit:

- `docs/standard-tier-review/STANDARD-DESIGN-SHEET.md` contains the current
  board-family, device-specific passive, layer, via, POFV, and release rules.
- `beta/atx-24pin-rev3/LAYOUT-GUIDE.md` was rewritten for the current six-layer
  ATX design. The obsolete Quilter file now redirects to it and cannot be read
  as an active constraint set.
- `hubs/hub-standard/LAYOUT-GUIDE.md` was rewritten for BETA Hub rev2 and the
  deliberate placement-redesign boundary.
- The June placement strategy, July routing foundation, pour-lever scoping,
  pour refinement, slab architecture, and August 1 audit are labelled as
  historical or superseded where their claims are no longer current.
- The June mezzanine draft is labelled superseded. The July segmented study is
  retained as rationale, while the August owner decision controls J6P/J6C/J6D
  and the fitted H1 M2 ground lug.
- PNG and SVG routing and placement plans are measured visual snapshots. They
  are not pipeline authority and must not override the current schematic,
  owner record, or design sheet.

## Owner inputs still required

The following choices cannot be derived safely from the current files:

1. Approve a worst-case wired-mode 3.3 V load budget for each controller board,
   or select a different regulator. No replacement regulator has been chosen.
2. Approve the LP5907 input, output, and ESP bulk-capacitor network after the
   regulator decision. Do not add 22 uF blindly.
3. Select the protection thresholds and divider tolerances for the nine
   TPS2121 OVP findings.
4. Select exact missing bypass and stability capacitors, including dielectric,
   voltage rating, package, MPN, and order code.
5. Select orderable mating header and socket parts for J6P, J6C, and J6D, plus
   the validated stack height.
6. Select or redesign the ARGB SATA input connector, NTC, PPTC, and PMOS power
   path for the declared current and ambient range.
7. Reconcile the ATX and Hub board-current tables with the thermal
   configurations. The audit will continue to block while they disagree.
8. Verify the exact high-current six-layer selector and 2 oz outer option in the
   JLCPCB order interface before release.
9. Choose the M2 hardware finish, washer, torque, and ground-bond acceptance
   limit from supplier data or measured samples.

## Primary sources

Fabrication and stackup:

- https://jlcpcb.com/capabilities/pcb-capabilities/
- https://jlcpcb.com/help/article/pcb-via-covering
- https://jlcpcb.com/news/free-via-in-pad-6-20-layer-pcbs-pofv
- https://jlcpcb.com/impedance
- https://jlcpcb.com/help/article/multi-layer-pcb-standard-laminated-structures
- https://jlcpcb.com/fr/help/article/jlcpcb-copper-weight

Device behavior and application circuits:

- https://www.ti.com/lit/ds/symlink/lp5907.pdf
- https://www.ti.com/cn/lit/ds/symlink/tps2120.pdf
- https://www.ti.com/kr/lit/gpn/ina240
- https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf
- https://www.ti.com/lit/ds/slvsdm5/slvsdm5.pdf
- https://www.ti.com/lit/ds/symlink/ref3030.pdf
- https://cache.nxp.com/docs/en/data-sheet/TJA1051.pdf
- https://documentation.espressif.com/esp-hardware-design-guidelines/en/latest/esp32c6/index.html
- https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c6/schematic-checklist.html

Exact passive selections were checked against Samsung Electro-Mechanics,
LCSC, UMW, Littelfuse, AOS, and the local manufacturer datasheets listed by
`scripts/cec_beta_electrical_audit.py`. The machine-readable finding record is
`build/audit-current/beta-electrical-passives.json`.

## Reproducible artifacts

- Electrical and passive findings:
  `build/audit-current/beta-electrical-passives.json`
- Fresh DRC reports: `build/audit-current/drc-all-beta/`
- Hub field result:
  `build/audit-current/fem/hub-design-basis-60C.json`
- 12VHPWR field result:
  `build/audit-current/fem/12vhpwr-design-basis-balanced.clean.json`
- Six-layer route round trip:
  `build/audit-current/route-6layer-smoke/`

Build artifacts are intentionally not release files. The committed scripts,
tests, schematics, BOMs, and current design documents define the reproducible
work.

## Final verification record

- Fresh KiCad 10.0.4 error-level ERC: 11 of 11 BETA root schematics passed.
- Fresh console ngspice bounded DC run: 11 of 11 BETA projects passed with no
  findings or coverage gaps. Every result reports functional signoff as false.
- Host electrical, SPICE, freshness, design-sheet, and normalizer tests:
  91 passed and 27 environment-specific tests skipped.
- KiCad-focused six-layer, pour, freshness, and design tests: 80 passed, with
  5 subtests passed.
- Placement, pour, POFV, route, and mezzanine group: 203 passed, 14 skipped,
  with 5 subtests passed.
- Thermal and FEM group: 201 passed and 7 skipped.
- SPICE launcher and parser group after the GUI-override repair: 40 passed.
- `git diff --check` passed.

A full 1,459-test repository run exceeded its 10-minute limit and did not
produce a final result. A later schematic integration group was stopped because
its Windows child processes opened visible command windows. Those processes
were terminated and no full-suite pass is claimed. The bounded groups above
cover the files and subsystems changed by this audit.
