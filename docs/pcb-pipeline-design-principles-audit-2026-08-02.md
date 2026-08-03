# PCB pipeline design-principles audit — revised 2026-08-03

## Scope and release meaning

This is an independent audit of the automated placement, routing, copper, and
fabrication pipeline. It does not assume that the existing design notes or
checked-in candidates are correct. The audited current BETA inputs are exactly
the ten entries in `scripts/cec_beta_manifest.py`: 12VHPWR, ARGB, ATX rev3,
EPS rev3, Hub rev2, both PCIe products, and the three output daughterboards.
Discovery is manifest-only; archived or recursively discovered board folders
cannot enter the current audit.

`eps-8pin` is an older board and is not the EPS product under review. There is
one EPS product; `eps-8pin-rev3` is its current BETA implementation. Board
revision directories are lineage, not product variants.

The checked-in candidates are stale against their current schematics and are
not accepted as current physical evidence. A generated board is releasable
only when exact schematic freshness and every ratified, checkable hard or strong
post-route constraint pass. A good route score, a pretty rendering, or one clean
DRC category is not a release.

## Standards and fabrication basis

The concrete BETA fabrication profiles are the JLCPCB 1.6 mm six-layer
`JLC06161H-3313` Hub buildup (1 oz outer copper) and `JLC06162H-3313`
high-current buildup (2 oz outer copper). In1 and In4 are continuous GND planes;
ordinary routed layers are F, In2, In3, and B. The repository records the exact
selected buildup, copper thickness, adjacent dielectric thickness, and
dielectric constant instead of using the old generic four-layer approximation.

Current JLCPCB published capabilities used as manufacturing floors are:

- multilayer 1 oz trace/space 0.09/0.09 mm; multilayer 2 oz 0.15/0.15 mm;
- absolute multilayer drill 0.15 mm, 0.20 mm preferred, and minimum via land
  diameter 0.25 mm;
- plated through vias only for the selected ordinary process; the CEC profiles
  additionally require at least 0.20 mm drill and at most 8:1 board-thickness to
  drill aspect ratio;
- six-layer POFV uses filled and capped vias and accepts published via diameters
  from 0.15 to 0.55 mm;
- solder-mask bridge is 0.10 mm for 1 oz green and 0.20 mm for 2 oz.

Source: <https://jlcpcb.com/capabilities/pcb-capabilities/>. Vendor minimums are
not automatic design targets; the project profile or netclass may be larger.

USB 2.0 High Speed is checked against 90 ohm differential impedance, no more
than 3.81 mm (150 mil) intra-pair mismatch, a continuous adjacent GND reference,
and a same-layer, low-transition route. TI's guidance also recommends keeping
both legs on one layer, no more than two vias, no plane splits, and GND stitching
at transitions:

- <https://www.ti.com/lit/ug/sllu149e/sllu149e.pdf>
- <https://www.ti.com/document-viewer/lit/html/SLLA653/GUID-A4F1CD83-9D39-45B1-B7A5-0E03429E4305>

The present impedance calculation is a profile-specific closed-form
microstrip estimate. It is a useful rejection/advisory tool, not fabrication
impedance signoff. Final geometry must be confirmed with the fabricator's field
solver and impedance coupon/TDR. The selected close-reference buildup also
cannot realize an exact 120 ohm CAN differential section at the conservative
minimum trace width; the short PCB section is therefore a documented
discontinuity that still requires system SI and bench validation.

High-current ordinary traces use the project's conservative IPC-2221 inverse at
30 C allowed rise and 125% of the reviewed sustained current. That calculation
is a deterministic design floor, not a substitute for IPC-2152 correlation,
enclosure airflow, connector/contact loss, copper-production tolerance, or the
repository's electrothermal solver and first-article temperature tests.

## Findings and repairs

| Area | Audit finding | Repair and enforced behavior |
|---|---|---|
| Candidate truth | Route/thermal scores could be read from boards no longer matching the schematic. | Exact value, footprint, assembly state, and numbered-pad net signatures gate candidate use. Stale candidates remain explicitly rejected. |
| Release aggregation | The final router verdict selected only a small hand-maintained subset of constraints. A newly added ratified gate could silently be omitted. | The final verdict now fails closed on every ratified, checkable hard or strong gate. Only schematic/PCB synchronization is delegated to the pre-route intake because a build artifact has no sibling schematic. |
| Constraint CLI | `cec_constraints.py` returned process success even with blocking failures. | `--strict` now exits nonzero for a FAIL or ERROR blocker. |
| Result contract | The laid-pour checker returned a list rather than the checker tuple and was reported as an ERROR instead of a real result. | It now returns PASS/FAIL/N/A through the normal constraint interface and has fail/N/A regression fixtures. |
| Stackup/impedance | USB estimates used stale four-layer constants (`h=0.2 mm`, `Er=4.5`, `t=0.07 mm`) on every board. | Impedance and precision routing now resolve the exact current board profile: F-to-In1 0.0994 mm, Er 4.10, with 0.070 mm outer copper on high-current boards and 0.035 mm on the Hub. Legacy constants are labeled fallback-only. |
| Netclass carriage | Materialization deliberately dropped every class below 0.30 mm. USB and ordinary signal widths and via rules therefore disappeared before routing. | Every project class, wildcard pattern, and explicit assignment is copied into the materialized project. Differential width and gap are retained separately from ordinary trace width. |
| Router trust | Freerouting can return SES geometry smaller than KiCad netclass track/via assignments. | Immediately after SES import, every ordinary segment is raised to its assigned track or differential width and every via to its assigned land/drill. Oversized features are retained. The route is not moved; any widening conflict must fail subsequent DRC. Direct INA2xx Kelvin stubs are excluded from this mechanical widening and are owned by the dedicated zero-via/topology gates. |
| Netclass verification | Differential pair legs were checked against ordinary `track_width`, not `diff_pair_width`. | The hard post-route gate resolves physical pair nets and checks their actual differential trace width; it independently checks every via land and drill against its assigned class. |
| High-current width | The old checker used a hard-coded 1 mm rule, looked only at 12 V/`_HI` names, compared the maximum width found anywhere on a net, and exempted the whole net when any pour existed. A single wide segment or remote zone could hide an undersized segment. | Every segment on every reviewed >=1 A current-model net is checked individually against profile copper and reviewed current. Only a segment whose start, midpoint, and end are inside its own filled copper on the same net and layer is pour-exempt. Ground uses the same non-double-counted current model. |
| Via construction | The earlier gate checked only the through-via enum. | Every routed via must be plated through-board and meet profile drill, annular, and 8:1 aspect limits. The separate netclass gate enforces larger class land/drill values. Blind, buried, stacked, staggered, and microvias fail. POFV still requires the declared filled/capped profile and complete land-in-pad qualification. |
| Pair topology | Differential checking stopped at router/DRC success. It did not prove skew, common layer, transitions, or return reference. | A ratified hard physical-integrity gate checks USB and CAN leg discovery, skew, same layer set, equal and bounded via count, adjacency to a GND plane, sampled filled-GND coverage, sampled pair coupling, and nearby GND return vias at signal layer transitions. |
| Placement | Generic proximity rules did not prove the new power topology. | The pipeline has explicit one-owner bypass assignment, device-specific value qualification, a hard TLV62569 switch-cell distance rule, and one-per-pin TPS2121 bypass coverage. Global connector-facing and rework orientation remain partial as listed below. |
| Copper weight/DFM | Fabrication audit applied the high-current 2 oz value to the 1 oz Hub. | Copper weight now resolves from the board's current selected profile. Plated-hole aspect scanning was added to fabrication audit. |
| Current ownership | Hub thermal and synthesis maps described different currents, and the held logic rail could be mistaken for the 2.5 A port bus. | Shared mutually-exclusive mux stages and GND use 2.5 A; each protected port and USB VBUS use 0.5 A. The hold reservoir actually feeds the reviewed 195.654 mA worst-case-with-margin logic rail, not the port bus. Conflicting active current sources block instead of choosing one silently. |
| Internal cutouts | The reverse-LED footprint's courtyard modeled the body but not the fabrication clearance around its shine-through aperture; an unrelated current-limit resistor legally entered the cutout margin. | The footprint now encodes the 0.8 mm aperture margin in F.CrtYd. Six LED bypass capacitors form one rigid macro at 2.95 mm offset. Fresh Hub placement has zero pad, courtyard, and courtyard-to-edge/cutout violations. |
| Rigid blind-mate rows | Static pinning of J_SIG1 was overwritten by the intentional daughterboard row alignment, while moving only the stub would break the mating pitch. | TB1..TB10 and J_SIG1 are solved as one rigid row against fixed component and force-rail boxes. The current ATX uses a 0.52 mm whole-row translation and retains every pitch/order relationship. |

## Width and via acceptance chain

The correct-width/via claim is intentionally redundant:

1. The authoritative `.kicad_pro` defines ordinary trace width, differential
   width/gap, via land, via drill, patterns, and explicit net assignments.
2. Materialization carries the complete contract into the generated project and
   DSN.
3. SES import raises any undersized returned feature to that contract; it never
   shrinks oversized copper.
4. `netclass-geometry-conformance` measures every actual routed segment and via.
5. `trace-width-high-current` independently calculates the minimum for every
   >=1 A segment from current, copper layer, and profile.
6. `through-vias-only` independently checks type, drill, annular land, and
   aspect ratio.
7. KiCad DRC runs after normalization, so a width/via repair that creates a
   clearance violation is rejected rather than accepted as an automatic fix.
8. Filled-pour connectivity, DC resistance/current density, thermal/FEM, and
   fabrication checks remain separate release gates.

This means the router is not trusted to honor geometry, and a post-route fix is
not trusted merely because it wrote a file.

## Placement, rotation, layer-jump, and return-path coverage

The automated pipeline currently provides defensible hard coverage for:

- no footprint overlap and no pad outside the board;
- selected connector edge proximity, overhang/pad containment, and mandatory
  mount/ground-lug contracts;
- distinct owner-qualified bypass capacitors and switch-cell proximity;
- shunt/Kelvin topology, force-pour reservation, and hot/sensitive separation;
- high-speed common-layer routing, bounded/equal pair transitions, reference
  plane coverage, pair coupling, and transition stitching;
- legal routed layers with In1/In4 reserved as continuous GND;
- per-segment width, via construction, filled-pour integrity/connectivity,
  error-level DRC, and zero unconnected items.

It does **not** yet prove all industry layout judgment. The release remains
fail-closed where a check is present, but these areas require new automation or
explicit human review:

- connector mouth direction is inferred from edge/body geometry for selected
  families; it is not a universal semantic model of every footprint's mating
  direction;
- no universal pin-1, diode/capacitor polarity visibility, silkscreen
  orientation, probe access, hand-solder clearance, or rework-tool approach
  checker exists;
- selected footprints are not yet mechanically compared pin-by-pin with every
  manufacturer land-pattern drawing and 3D body envelope;
- courtyard checking is still footprint-quality-dependent. The current reverse
  LED and mezzanine footprints carry measured body/cutout extents, but the
  pipeline cannot infer a missing manufacturer courtyard from a generic land;
- solder-mask web, paste-reduction/windowing, stencil aperture separation,
  fiducials, tooling rails, panel/depanel stress, V-score/tab placement,
  castellations, and edge plating are not complete hard release gates;
- the closed-form impedance estimate is not a 2D field solver and there is no
  automated coupon/TDR result ingestion;
- electromagnetic emissions/immunity, USB eye/compliance, CAN margin, thermal
  calibration, connector mating/stack height, and durable shutdown are
  first-article or owner-selection gates, not CAD proofs.

## Current electrical release state

The 2026-08-03 manifest-only audit reports 21 blockers, 19 warnings and 28
information findings across ten projects:

- ATX rev3 and Hub rev2 have no electrical blockers. ATX requires 204.838 mA
  including 20% margin from the 500 mA TLV75533 (59.0% remaining). Hub requires
  195.654 mA from the 1.76 A conservative buck/inductor limit (88.9% remaining).
  The exact Samtec segmented mezzanine roles match. Hub retains four warnings:
  the OQ-56 bench proof and three 5.66..6.37 V TPS2121 OVP windows.
- 12VHPWR has one blocker: its 47k/10k TPS2121 OV1 divider can trip as high as
  6.374 V ahead of a 6.0 V-absolute-maximum regulator. Its reviewed TLV75533
  load is 212.327 mA (57.5% remaining).
- EPS rev3 has three blockers: the legacy Schottky USB OR path, an unapproved
  LP5907 capacitor network, and no reviewed 3.3 V load budget. This is the one
  EPS product; `eps-8pin` is not a variant or current input.
- ARGB has nine blockers: its U6 bypass, LP5907 network/load budget, unresolved
  SATA connector/footprint, and unproven NTC/PPTC/PMOS 7 A margins.
- Each PCIe board has four blockers: LP5907 capacitor/load qualification,
  TPS2121 OV1 margin, and a missing U4 IN1 local bypass. Two exact passive
  selections per board also remain warnings.
- The three output daughterboards have no electrical-audit findings, but still
  require mating/load/first-article proof.

The Hub hold-up topology watches the final selected `+5VSB` ahead of the
reservoir diode. Nominal trip is 4.355 V (bounded 4.060–4.663 V), retaining at
least 60 mV before the reviewed buck regulation floor. The conservative sudden
loss calculation gives 13.167 ms against a 10 ms trigger-to-durable-commit
budget, leaving 3.167 ms. This is a paper bound; OQ-56 bench validation remains
open for source decay, capacitor ESR/aging/temperature, load shedding, and
actual durable-write latency.

## Verification evidence

- Changed-script byte compilation: pass.
- Focused electrical, hold-up, six-layer, route-fail-closed, candidate,
  netclass, laid-pour, SPICE, and thermal-source regression group: 241 passed,
  5 skipped for unavailable/fixture-gated route cases.
- Added adversarial fixtures cover exact profile stackup selection, per-board
  copper weight, aggregate release FAIL/ERROR behavior, a clean USB pair with
  ground/coupling, asymmetric pair vias with a missing return via, SES
  track/via normalization, and laid-pour N/A/failure behavior.

### Fresh current-board measurements

The post-repair pipeline was exercised against the current manifest inputs, not
the archived EPS line or a stale dashboard entry.  These are diagnostic outputs;
none of these artifacts is releasable:

| Candidate | Via construction | Width result | Pair/return-path result | DRC / connectivity | Verdict |
|---|---|---|---|---|---|
| Hub rev2 R4/R7, 86x74 | Partial route has no sub-profile via land/drill, annular, type, or 8:1 aspect finding; placement R7 is 0 residual with buttons on F.Cu and six aperture-qualified LED bypass macros | Partial returned geometry has no sub-profile width finding, but that does not clear 38 missing connections | CAN skew is 5.0 mm against the 4.0 mm gate; thermal injection is incomplete on 9/12 requested rails | route polish leaves 90 structural DRC and 38 unconnected; independent fab pass has 34 DRC, 13 acid-trap candidates, zero slivers/islands | BLOCKED; clean placement is visual evidence only |
| ATX rev3 R4, 86x95 | All four forced rails lay with profile widths/via arrays; existing locked copper has no sub-profile via/aspect finding | Existing locked copper has no sub-profile width finding; freerouting returned no completed signal route | No routed pair/return result exists because routing plateau-killed | all twelve placement variants were residual 0, but the route plateau-killed at 218/186 and the placement artifact has 310 unconnected | BLOCKED; placement/rail proof only |
| 12VHPWR `20260802T2350-plain-compact-s0` | PASS: 104/104 routed vias are plated through-board and meet the selected profile's drill, annular-land, and 8:1 aspect rules | FAIL: 293 current-model segments are undersized; representative SENSEP lanes use 0.25-1.40 mm where the current model requires 2.239 mm outside a qualifying same-net fill | FAIL: lane-pair skew is 15.51 mm with only 29.7% coupled coverage; USB naming also prevents automatic P/N recognition | 30 structural DRC findings and 102 unconnected items in the wave gate | BLOCKED |
| EPS rev3 `20260802T2351-periph-right-dataflow-s1-polish` | PASS: 84/84 routed vias are plated through-board and profile-dimensional | FAIL: 177 current-model segments are undersized | FAIL: USB skew 5.81 mm and 33.0% coupled coverage; CAN skew 5.34 mm, 91.5% adjacent filled-GND coverage, and 20.3% coupled coverage | 4 structural DRC findings, 27 unconnected items, and 5 acid-trap candidates in the independent fab pass | BLOCKED |

The 12VHPWR and EPS route artifacts also fail the device-specific
decoupler-owner gate, via-in-pad qualification, and visible silkscreen review.
Their 3D renders show overlapping
references and values; the current silk metric is only a soft score and does not
prove label legibility or a universal readable orientation.  This remains an
explicit automation gap: a future board is not accepted from a visually crowded
render merely because the copper gates pass.

The dashboard was repaired to read the authoritative ten-project BETA manifest
(including only `eps-8pin-rev3`) and to run its analyzer natively when Docker is
not installed or accessible.  Native fallback avoids a duplicate routing image
on clean WSL installations while preserving the same panel and gate contract.

Fresh route evidence is recorded in the wave reports, while the current
placement renders are in `output/review/` and the dashboard's local analyzed
archive. A refusal or failed ratified constraint is evidence that the
pipeline worked; it is not replaced with a stale candidate for presentation.

## Release conclusion

The repaired automation is materially stronger and now has a credible,
fail-closed chain for assigned trace widths, differential widths, vias,
high-current segment sizing, pair reference continuity, and selected-profile
fabrication limits. It is still not correct to call any primary BETA PCB
fabrication-ready until a fresh exact-schematic board passes the whole aggregate
gate and the listed component, connector, field-solver/fabricator, and
first-article obligations are closed.
