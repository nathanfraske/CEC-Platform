# PCB physics and methodology review — 2026-11-05

## Disposition and scope

**Review only. No PCB/SI/EMC qualification performed by this review.** No PCB,
schematic, process setting, electrical budget, firmware, gate, or mechanical
interface was changed. No simulation, receiver campaign, hardware test, or
fabrication release was run. Sources were inspected on 2026-11-05. Existing
reports are attributed evidence, not newly executed or automatically transferred
to a different board hash.

The audit intake captured from `checkpoints/current.json` at the start named
`checkpoints/review-20261105-atx-refinement/receipt.json` with SHA256
`33d752bae179fede25a4e90543d02c95bbcc6071bedcf26a6bc7925c1333f8a7`.
Its nine boards each report zero native errors, zero opens, and zero exclusions.
Warnings remain: ATX 67, Hub 28, 12VHPWR 105, EPS 45, PCIe two-port 19,
PCIe three-port 19, and zero on each output daughterboard; total 283.
This is a native connectivity/DRC checkpoint, not SI, PDN, thermal, EMC,
production-process, or assembled-product approval.
The live pin may advance through separately received polish; this report names
its exact audit baseline rather than claiming automatic requalification of a
later board hash. No parts, interfaces, stackups or dimensions changed in the
associated polish pass.

The supported workflow is `docs/agent-directed-pcb-pipeline.md`: a frontier
agent chooses explicit geometry; bounded deterministic workers construct it;
independent receivers check saved candidates. This review does not propose
reactivating retired autonomous waves or replacing source-owned requirements
with model-authored electrical assumptions.

## Actual interface and device inventory

Values below were observed in the actual current checkpoint PCB files, not
inferred from a board name or the wider platform roadmap.

| Board family | Observed controller / measurement parts | Interfaces relevant to this review |
| --- | --- | --- |
| Hub Standard | ESP32-S3-WROOM-1; TJA1051T/3; TLV62569DBVR; TLV7011DBVR; TPS2121RUXR; USBLC6-2SC6 | Native USB Full Speed, shared classical CAN, local control / LED / power-management signals |
| 12VHPWR Standard | ESP32-S3-MINI-1-N4R2; INA240A3; REF3030; TJA1051T/3; TPS2121RUXR; USBLC6-2SC6 | USB Full Speed, classical CAN, low-level shunt / reference / ADC paths |
| ATX, EPS, PCIe two-port, PCIe three-port | ESP32-C6-MINI-1-N4; INA238; INA181A2IDBVR; TLV7011DBVR; TJA1051T/3; TPS2121RUXR; USBLC6-2SC6 | USB Full Speed, classical CAN, monitor I2C and local analog / fault / control paths |
| ATX / EPS / PCIe output daughterboards | Passive high-current terminal / connector assemblies | Current-carrying copper, plated barrels, bolted contact and mechanical / thermal paths; not high-speed serial channels |

Production source policy is classical CAN at **500 kbps**, not CAN-FD:
`CLAUDE.md` records the platform-wide deferral of CAN-FD, and
`scripts/cec_constraints.py` identifies TJA1051T/3. The README's older Pro
CAN-FD statement must not override this decision. The PCIe board names identify
power connectors; no PCIe SerDes requirement follows from those names.
ESP32-C6's integrated USB Serial/JTAG controller is Full Speed, up to
12 Mbit/s [S1]. The Standard S3 boards are also scoped as USB Full Speed.
Do not apply 480-Mbit/s USB HS, PCIe-generation, Ethernet, or RF channel budgets
from higher-tier exploratory designs to these nine boards.

The production controller choice is not proof of the configured production
firmware timing. The shared INA226/INA228 firmware defaults include 400-kHz
I2C, but these do not establish the actual INA238 configuration on each
reviewed board. Actual I2C pull-ups, aggregate pin/cable/trace capacitance,
configured rate and rise-time margin still need per-board source binding.
GPIO/SPI/LED edge rates must likewise be established from the actual driver,
configuration, and load, rather than equating low data rate with slow edges.

### Preserve the no-radio / ignored-antenna decision

`CLAUDE.md` explicitly drops the Standard antenna keepout for the wired-only
design and records the EPS C6 no-wireless decision. The
`esp-antenna-keepout` constraint is conditional on radio use and explicitly
allows dropping it on a wired-only board. This review **does not propose radio
use, restoring antenna clearances, antenna tuning, or RF fencing around the
unused antenna**. Espressif's USB and power-layout guidance remains relevant;
its antenna-specific guidance must not silently reverse the owner's decision.
Any future request to enable radio would be a separate design and qualification
change. Wired-only status does not itself establish unintentional-radiator EMC
compliance; no regulatory exemption or certification-cost claim is made here.

### Bring-up evidence is not the production channel

`firmware/esp/proto/hub-standard/README.md` describes a Lonely Binary
development board and SN65HVD230 breakout, defaulting to **125 kbps** because of
the breakout's slope-control resistor; 500 kbps is the platform target.
Its bench recommendation for termination at both ends does not supersede the
locked production Hub-only split termination / no module termination contract.
Successful prototype traffic is not evidence that the production four-port
channel passes at 500 kbps with all allowed cables and populations.

## What is already implemented, and its qualification boundary

| Area | Existing inspected implementation / evidence | What it does not establish |
| --- | --- | --- |
| Process ownership | `cec_fab_profile.py`, constraints and declared native properties; process-qualified POFV eligibility; through-via-only policy | A live supplier order, guaranteed material tolerance, manufactured coupon or lot acceptance |
| Local decoupling | `cec_decoupler_cell.py` owns supply-pin to value-qualified capacitor to immediate ground-entry cells; explicit return routing and process rules | Extracted loop inductance, capacitor impedance under bias/temperature, regulator stability or rail transient margin |
| Differential geometry | Coupled routes, endpoint handling, `cec_pair_skew.py`, pair returns and physical reference checks | Full channel propagation delay, calibrated impedance, mode conversion or receiver waveform margin |
| Return transitions | `cec_pair_return.py`, `cec_pth_pair_returns.py`, `cec_field_transition_return.py` require actual filled reference contact, not merely a nearby via | Every discontinuity's electromagnetic impedance, package/connector models, or absolute SI qualification |
| Field separation | `cec_field_coupling.py` classifies explicit electrical roles and checks geometry and actual intervening filled GND shielding | Extracted mutual C/L, quantitative coupled noise, all unclassified nets, or whole-product EMC |
| Power / Kelvin | Independent current debt, source-owned current requirements and Kelvin copper-cut / noninterference receiving | A new current rating, barrel capacity, whole-board absolute Kelvin qualification or thermal release |
| Assembly | Declared paired-board envelopes, retained datum / contact / vent contracts | Supplier tolerance validation, incoming samples, torque/retention, cable sweeps or measured assembled fit |
| Native acceptance | Hash-bound saved candidate, DRC / opens / preservation and capability-specific checks | Fabrication or production release; a nonregression result may preserve known debt |

The workflow already separates ordinary signals from power, sense, clock and
paired nets. Ordinary-route receiving does not authorize paired/high-current
reconstruction; `add_connections` excludes power and paired routing. Missing
high-speed treatment should not be addressed by bypassing these authority
boundaries.

**Enabled-path distinction:** retained pair-return/skew/reference validators
are not equivalent to a mandatory complete-channel gate in the new workbench.
The active capability catalog and receiver dispatch do not invoke the complete
`high-speed-pair-physical-integrity` checker in `cec_constraints.py`.
`cec_field_coupling.py` is an aggressor/victim interaction screen; it skips pair
mates and does not, by itself, prove an isolated pair's return continuity over
a plane slot. Wiring a source-bound complete-pair/return observer into relevant
transactions, with slot/disconnected-island/unmatched-transition canaries, is
an outstanding implementation slice. No new SI pass is claimed here.

Likewise, no separate enabled acid-trap/copper-sliver finishing audit was found
in the active workbench. Installed KiCad mask/copper/drill rules retain their
existing coverage; manufacturing finishing must independently enumerate what
the selected process requires rather than relabel native closure as complete
DFM acceptance.

### Stackup and layup: declared, verified and still provisional

The six active boards have owner-approved six-layer process decisions, not a
missing generic stackup:

| Process | Declared buildup | Copper | Layer roles / dielectric distances |
| --- | --- | --- | --- |
| Hub signal | JLC06161H-3313; 1.6 mm | 35 um outer; 15.2 um inner | SIG / GND / SIG / PWR / GND / SIG; 0.0994 / 0.55 / 0.1088 / 0.55 / 0.0994 mm |
| High-current active boards | JLC06162H-3313; 1.6 mm | 70 um outer; 15.2 um inner | SIG-PWR / GND / SIG / PWR / GND / SIG-PWR; 0.0994 / 0.55 / 0.0994 / 0.55 / 0.0994 mm |

The named Hub buildup and its dimensions are visible on JLCPCB's current
controlled-impedance page [S4]. The rendered page inspected on 2026-11-05 has
**no match for JLC06162H-3313**. That absence is not proof of unavailability;
the repository records an August 1 supplier selection and owner decision.
It means current supplier confirmation of the exact high-current buildup,
finished copper, material/tolerance and POFV process is still required before
calling it currently supplier-qualified. Preserve its source decision while
obtaining that confirmation; do not silently replace the process.

The three output daughterboards are separate **four-layer exceptions**.
`docs/standard-xfcn-electrothermal-validation-2026-08-12.md` describes ATX
70/70/70/70-um copper and EPS / PCIe 70/35/35/70-um copper at 1.6 mm.
These are not permission to apply the six-layer signal model or its POFV
assumptions to the daughterboards. Supplier order and current native identity
must be reconciled to each specific board before fabrication.

The active six-layer architecture has close outer signal-to-GND spacing, but
the declared inner signal layer is close to power on its other side. A layer
role does not guarantee an uninterrupted high-frequency return, and an outer
microstrip formula does not describe an inner trace with multiple references.
Reference continuity, actual plane fill, layer assignment and transitions must
be received for each relevant path. No layer-count change is recommended here.

### Impedance and parasitics: useful advice is not calibrated signoff

`scripts/cec_impedance.py` explicitly labels its closed-form impedance,
Kelvin loop-area and parallel-run calculations **advisory**. Its coupled
microstrip approximation is described as approximately 10%-class; it uses
nominal netclass width/gap and selected dielectric/copper geometry. It does not
solve each saved route's pads, width changes, vias, soldermask, copper shape,
roughness, frequency-dependent dielectric, or connector/package discontinuities.
The selected fallback must remain labelled; legacy four-layer constants are
not valid authority for a current six-layer channel.

Espressif specifies 90-ohm differential USB impedance with +/-10% tolerance,
parallel equal-length routing, continuous reference, minimized transitions,
ground-return vias at required transitions and surrounding GND copper [S2,S3].
Those actual-device requirements are relevant despite Full Speed operation.
Do not use a closed-form estimate whose uncertainty approaches the complete
tolerance band as fabrication acceptance evidence.

`cec_pair_skew.py` preserves existing 3.81-mm USB and 4-mm CAN summed
straight-copper length-difference limits. These are existing repository limits,
not newly justified electrical budgets. The method is not full propagation
delay through packages, vias, pads and layer-dependent dielectric, and sums
straight `PCB_TRACK` geometry. Branched/flow-through routes and any arc paths
need explicit semantic coverage tests. No tighter budget is invented here.

## Curves, fences, guarding and standard practice

Purposeful 45-degree routing, short routes and controlled transitions are
appropriate defaults. Universal circular routing is not a missing safety gate:
an arc cannot repair a broken reference plane, uncontrolled spacing or a poor
connector launch. RF miter/arc advice is interface-specific and does not create
an RF use case on these no-radio boards. Do not add meanders merely to meet an
invented length target.

Ground fill / fences can provide local shielding and return paths when they
are genuinely connected to the reference and included in the impedance model.
Espressif explicitly requests ground around USB [S2,S3]. They are not an
independent cure: close coplanar copper changes capacitance and impedance;
poorly connected long copper is not an equipotential RF shield; dense via
antipads can perforate a useful plane; and a fence can consume required
clearance or make an existing path worse. Geometry, return topology, process
clearance and relevant electrical margin must be checked together [S5].

A grounded shield is not the same as a driven leakage guard. A guard around
a high-impedance node may need to follow that node's potential to prevent
surface leakage [S10]. That does not justify automatically surrounding the
low-ohmic shunt inputs with driven guards or changing Kelvin topology.
For these boards, first preserve Kelvin taps, input symmetry, filtering,
reference cleanliness and source-owned measurement bandwidth [S9].

Orthogonal routing on unshielded adjacent layers is a useful geometric
coupling control, not proof of zero coupling. A real continuous intermediate
GND plane changes the problem; a declared plane without saved copper does not.
Keep the existing conservative field gate, including its visible EPS debt,
while adding selective quantitative analysis only where a source-owned noise
or timing budget can receive the result [S5,S8].

## Prioritized bounded implementation and verification plan

Each slice should produce a finite, hash-bound report with explicit complete,
fail and unknown states. Preserve existing owner current / thermal / accuracy
budgets, netclasses, locked termination, process exceptions and mechanical
datums. New numeric budgets require source authority, not model convenience.

1. **P0: Freeze the electrical requirements matrix.** Bind each actual
   interface to pins, part/package, production firmware configuration, rate,
   fastest relevant edges, load, topology, termination, tolerances and primary
   source. Enumerate unknown inputs explicitly. Test that an unknown or changed
   driver/configuration invalidates qualification rather than inheriting it.

2. **P0: Reconcile the physical process.** Obtain dated supplier confirmation
   of each exact six- or four-layer buildup, finished copper, dielectric and
   thickness tolerance, material identity, mask, PTH plating, POFV, minimum
   spacing and assembly options. Compare declared native stackups and order
   constraints per board. Test a changed buildup, missing declaration, wrong
   four-layer exception and unqualified via process as refusals.

3. **P0: Receive actual USB transmission geometry.** Extract each connector,
   protection leg and controller path, width/gap variations, face, local
   reference and return transitions. Bound initial extraction to one S3 and one
   C6 channel; then cover the remaining instances. Compare a suitable 2-D
   cross-section result with the supplier calculator and manufactured coupon /
   TDR where applicable, with mask/copper/dielectric corners. Do not adopt
   nominal netclass impedance as calibrated acceptance.

4. **P0: Receive return-path continuity.** Produce full-path reference coverage
   and actual grounded return witnesses for each transition and PTH launch.
   Add hostile fixtures for a plane slot, a disconnected nearby ground island,
   via antipad perforation, and a return via that misses a required reference.
   A nearby barrel that does not contact the filled reference must fail.
   Retain existing source-owned return-reach limits; do not import another
   processor's general app-note limits as a waiver.

5. **P1: Close pair semantic coverage.** Test branches, USB protection
   flow-through legs, cumulative skew, unequal via count/layers, and arcs.
   Report existing geometric limits separately from electrically sourced
   propagation-delay margin. No geometry receiver should silently omit a
   branch or count copper on an unrelated path as its length match.

6. **P1: Qualify the production CAN channel.** Retain Hub-only split
   termination / no module termination. Establish actual allowed cable
   lengths, port topology, branch lengths, populations, connector / choke /
   protection parasitics, bit timing and TJA1051 operating corners. Select a
   finite worst-case channel set, then receive waveforms / sampling margin at
   the 500-kbps production target. Keep prototype 125-kbps traffic separate.
   Supplier CAN guidance supports the analysis, not a unilateral architecture
   change [S6,S7].

7. **P1: Extend local decoupling into a bounded PDN study.** Start with one MCU
   rail and one measurement/reference rail. Require actual capacitor MPNs,
   DC-bias/temperature/aging/ESR/ESL curves, regulator stability requirements,
   source impedance, package and via/plane geometry, allowed ripple, and
   source-owned load steps. Analyze loop L, resonances, damping and rail
   droop. Correlate with short-loop probing / impedance or load-step data.
   Do not invent target impedance or add arbitrary capacitors/ferrites;
   additional parts can change resonance or regulator stability [S11].

8. **P1: Quantify only critical analog interactions.** Prioritize INA240 /
   INA238 / INA181 inputs, REF3030 and fault-comparator paths near switch,
   clock and USB activity. Require victim impedance, bandwidth and allowable
   input-referred error plus actual aggressor edges. Extract selective mutual
   C/L or a suitable reduced model and compare predicted / measured noise
   with that budget. Spacing ratios alone are not absolute noise proof [S8,S9].

9. **P1: Receive deliberate ground-fill / fence changes.** Treat them as
   electrical geometry, not cosmetic cleanup. Check actual reference contact,
   impedance change, plane integrity, field nonregression, native clearance and
   process limits. Permit them only when an interface-specific rationale and
   evidence support the change. Preserve the no-radio / ignored-antenna
   decision; do not add antenna or RF redesign to this slice.

10. **P0 release: Close thermal, assembly and EMC independently.** Preserve
    current/Kelvin/barrel gates and retained release holds. The August XFCN
    report records cold copper-path passes but an isolated-board thermal-screen
    failure and requires representative terminal/cable/fastener heat paths or
    correlated 3-D / hardware evidence. It is not a fresh current-checkpoint
    thermal result. `docs/hub-atx-stack-qualification-status.json` remains
    `PROTOTYPE_BLOCKED`: supplier tolerances, torque/thread/bow, plug/latch
    sweeps, cold/aged capacitors, startup and measured physical fit remain
    distinct evidence. Receive representative assembled samples at existing
    owner-defined limits. Component ESD ratings do not establish assembled
    system immunity or EMC [S12].

The important missing progression is from **geometrically preserved /
provisionally modelled** to **source-budgeted, calibrated and assembly-qualified**.
The suite already contains substantial normal PCB practice; adding generic
curves, fences, a different stackup, or an attractive grid is not that progression.

## Primary references and version / retrieval notes

All URLs below are primary manufacturer sources inspected on **2026-11-05**.
Live pages are not immutable releases; save the specific document version/hash
when an implementation slice makes them load-bearing. Manufacturer guidelines
for other processors are methodology references, not authority for replacing
CEC's actual-device numeric requirements.

- **S1 — Espressif, ESP32-C6 datasheet.** Live PDF; USB Serial/JTAG Full Speed
  capability. A specific datasheet revision was not frozen by this review.
  <https://www.espressif.com/sites/default/files/documentation/esp32-c6_datasheet_en.pdf>
- **S2 — Espressif, ESP32-C6 PCB Layout Design.** Live `latest` hardware-design
  guidelines; USB impedance, equal-length routing, continuous reference and
  paired return vias. <https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c6/pcb-layout-design.html>
- **S3 — Espressif, ESP32-S3 PCB Layout Design.** Live `latest` guidelines;
  actual-device USB and module/baseboard methodology. Antenna advice is not
  activated for the wired-only CEC decision.
  <https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html>
- **S4 — JLCPCB, Controlled Impedance PCB Layer Stackup.** Live supplier page;
  named Hub buildup verified; high-current named buildup not found in the
  rendered page. <https://jlcpcb.com/impedance>
- **S5 — Texas Instruments, High-Speed Interface Layout Guidelines,
  SPRAAR7J, revised February 2023.** Reference planes, stitching, differential
  geometry and discontinuities. Processor-specific appendices are not ESP32
  requirements. <https://www.ti.com/lit/an/spraar7j/spraar7j.pdf>
- **S6 — NXP, TJA1051 High-speed CAN transceiver, Rev. 9,
  28 November 2017.** Actual selected transceiver, operating and timing
  characteristics. <https://www.nxp.com/docs/en/data-sheet/TJA1051.pdf>
- **S7 — Texas Instruments, Controller Area Network Physical Layer
  Requirements, SLLA270, January 2008.** Bus topology, loading and physical
  channel analysis. <https://www.ti.com/lit/an/slla270/slla270.pdf>
- **S8 — Texas Instruments, regulator signal-routing / crosstalk technical
  article, SSZT935, October 2017.** Coupling depends on rise time, spacing,
  reference-plane distance and parallel length; sensitive analog consequences.
  <https://www.ti.com/document-viewer/lit/html/SSZT935/GUID-0FCA647D-9DF5-4B70-AFC8-2E976F7A12D6>
- **S9 — Texas Instruments, INA240 datasheet, SBOS662C,
  revised December 2021.** Actual 12VHPWR amplifier's Kelvin and bypass layout
  requirements. <https://www.ti.com/lit/ds/symlink/ina240.pdf>
- **S10 — Analog Devices, A Practical Guide to High-Speed Printed-Circuit-Board
  Layout.** Manufacturer article; no immutable revision asserted here.
  Distinguishes shielding and high-impedance guarding.
  <https://www.analog.com/en/resources/analog-dialogue/articles/high-speed-printed-circuit-board-layout.html>
- **S11 — Analog Devices, MT-101 Decoupling Techniques, Rev. 0,
  March 2009.** Connection inductance, capacitor self-resonance and damping.
  <https://www.analog.com/media/en/training-seminars/tutorials/MT-101.pdf>
- **S12 — STMicroelectronics, USBLC6-2 datasheet.** Live PDF, specific
  revision not frozen by this review; protection capacitance and device-level
  ESD scope. <https://www.st.com/resource/en/datasheet/usblc6-2.pdf>
