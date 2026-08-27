# PSU Tester program — stop-work and reconciliation gate

**Status: STOP WORK — mandatory program gate, effective 2026-08-10.**

This document blocks implementation work on every board and mechanical assembly
under `testers/` until the findings below are reconciled. It applies to Tester
Standard/ST-1000/ST-1300, Pro, Max, fast-channel slices, slot decks, fixture
heads, resistor-bank walls/cartridges, and their shared electrical interfaces.

## 1. Work that is blocked

Until this gate is released, do not:

- create or revise production-intent Tester schematics, PCB layouts, stackups,
  footprints, harness definitions, or mechanical drawings beyond changes made
  specifically to close a gate item below;
- order Tester PCBs, assembled boards, production resistor banks, cartridge
  metalwork, or production connector quantities;
- treat generated leaf schematics as a complete, ERC-cleared design;
- copy the present Standard power/load cells into Pro, Max, or SE variants;
- advertise or record any Tester tier as electrically, thermally, mechanically,
  or sourcing complete.

Read-only analysis, simulations, supplier/RFQ work, bench coupons, and narrowly
scoped reconciliation prototypes are allowed. Every such change must identify
the gate item it closes and retain before/after evidence.

## 2. Findings that require reconciliation

| ID | Finding | Required disposition and evidence |
|---|---|---|
| TST-G01 | `gen_tester_st.py` assigns the generic 0402 footprint to every `R_Small`. The emitted 12 V loop therefore places both 0.1 ohm source-ballast parts and the Bourns CSS2H-2512 1 milliohm shunt on 0402 lands. The bank rail shunts inherit the same error. | Give every power resistor and shunt an exact manufacturer part, rated footprint, thermal/current calculation, and documented sense-trace connection. Regenerate the sheets and prove the emitted footprints match the BOM. |
| TST-G02 | OPA2277 is powered from 3.3 V while its minimum total supply is 4 V; it is not rail-to-rail and its input common-mode range excludes the near-ground millivolt shunt signal. | Select an amplifier and supply that cover ground-referenced input, required gate swing, output-current/capacitive-load behavior, offset, fault states, and temperature. Provide a reviewed loop schematic plus operating-point and stability evidence. |
| TST-G03 | A raw 0 to 3.3 V PWM setpoint is compared directly with a 1 milliohm control shunt. Intended 2 A and 5 A commands correspond to only 2 mV and 5 mV, making useful resolution, ripple, and calibration impractical. | Establish a documented setpoint and feedback range, including DAC/PWM resolution, filtering, control-shunt value, amplifier scaling, offset/error budget, startup/shutdown behavior, and compensation. Verify it on a representative CC-loop coupon. |
| TST-G04 | One 1 milliohm CSS2H-2512 rail shunt is asked to carry 64 A in ST-1000, 88 A in ST-1300, and approximately 106 A in Pro/Max. Its dissipation is approximately 4.1 W, 7.7 W, and 11.2 W respectively, while the selected 1 milliohm part is rated 5 W at its specified terminal condition. | Re-size the shunt network for every tier and fault transient. Provide continuous/pulse power, terminal-temperature, sense-connection error, amplifier-range, and trip-threshold evidence. A symmetric parallel-shunt candidate must include current-sharing analysis. |
| TST-G05 | The 12 V ladder places up to 16 legs/32 A on one AOD4184A in ST-1000 and describes a 28-leg/56 A population in ST-1300. At the part's maximum 4.5 V `RDS(on)`, the nominal losses are approximately 9.7 W and 29.8 W before hot-resistance increase. | Cap group current or redesign the switch. For every group, document FET count, gate voltage, DC SOA, hot `RDS(on)`, copper/heatsinking, current sharing, fuse rating, and fault interruption. Validate the hottest group on a thermal coupon. |
| TST-G06 | Keystone 3557-class ATO fuse hardware is a 30 A class holder, below the current of the 32 A and 56 A groups. | Split groups or select qualified higher-current protection. Fuse and holder must be derated for enclosure temperature and must coordinate with FET, shunt, copper, connector, and resistor fault energy. |
| TST-G07 | The resistor ladder is not backed by a production-ready exact-value family. The live LCSC line previously used as its pricing basis is 5 ohm, not the specified 6 ohm, has insufficient depth for production, and changes a 12 V leg from 2.0 A/24 W to 2.4 A/28.8 W. The 1 ohm, 0.68 ohm, and 3.3 ohm requirements are not locked to one qualified stocked housing family. | Lock exact manufacturer part numbers, tolerance/TCR/pulse behavior, mounted-power derating, terminal style, sourcing depth, alternates, and tier quantities. Recompute every ladder current, fuse, switch, shunt, airflow, and firmware calibration constant from the locked values. |
| TST-G08 | The current off-board resistor footprint is a two-wire landing, while the later wall-cartridge architecture prohibits discrete leg wiring and assumes a blade-drop interface. | Choose one interface and carry it consistently through schematic, PCB, BOM, mechanical drawing, assembly process, and service procedure. Remove the contradictory footprint or formally retain it only for an identified bench variant. |
| TST-G09 | A 16 to 32 contact wall creates a spec-bound gang insertion/removal load of hundreds of newtons. Connector tolerance cannot register or support the resistor wall. The exact lower screw-tab mating part is not locked, and the lower-insertion-force 0.025 inch receptacle candidate is not compatible with the existing 0.032 inch platform tab. | Produce a keyed, chassis-supported cartridge design in which guides engage before contacts, receptacles have controlled float, blades carry no structural load, and a lever/cam supplies the measured force. Lock a thickness-compatible mating pair and complete fit, 20-cycle wear/contact-resistance, thermal-rise, vibration, and service tests. |
| TST-G10 | The proposed shared back-to-back mounting bolts, plate, thermal interface, airflow, hot-surface protection, terminal-to-case insulation, sensors, and independent over-temperature cutoff have not been qualified as one assembly. | Release a mechanical/thermal drawing with individual clamp-load control, flatness and torque requirements, TIM, grounding/insulation treatment, bus/adapter strain relief, wall support, airflow direction, NTC placement, independent NC cutoff, and guarding. Correlate the thermal model to an instrumented wall coupon. |
| TST-G11 | Tester Standard consists of generated leaf schematics but has no complete top-level project/PCB release; its referenced checker is absent, and the ST-1300 additional legs are documented but not physically captured. Pro and Max remain architecture-only. | Build a complete Standard root schematic and PCB source of truth. Pass the repository's electrical audit, KiCad ERC, BOM/footprint consistency, netlist-to-PCB equivalence, DRC, fab checks, and a peer review. Only then derive Pro/Max cells. |
| TST-G12 | LCSC availability and an EasyEDA model are being conflated with JLCPCB assembly readiness. Several blade/mechanical parts are extended, wave-soldered, out of stock, or necessarily installed off-board. | For every non-SMT or mechanical item, record JLC assembly type, current stock, feeder/loading or wave/manual process, consignment/global-sourcing plan, MOQ, alternates, and who installs it. Chassis resistors and cartridge hardware must have a separate assembly traveler. |

## 3. Required resistor-wall prototype

Before any full wall or production deck is released, build one representative
sub-cartridge containing 6 to 10 lower blade joints (approximately three to
five back-to-back resistor positions). It must use the intended wall material,
mounting hardware, thermal interface, feed/return conductors, blade adapters,
floating receptacle carrier, guide features, and insertion tool.

Record at minimum:

- cold and stabilized contact resistance for every joint;
- insertion and extraction force on cycle 1 and cycle 20;
- resistor-case, plate, terminal, receptacle, PCB, FET, fuse-holder, shunt, and
  exhaust temperatures at worst continuous load and fan-fault shutdown;
- visible movement, fretting, fastener relaxation, insulation damage, or solder
  distress after thermal cycling and vibration;
- over-temperature cutoff independence from firmware and its safe de-gate path.

## 4. Release authority and evidence

This stop-work status may be removed only by an explicit owner decision after a
review packet contains all of the following:

1. a disposition for every `TST-Gxx` row: **fixed**, **accepted with quantified
   limit**, or **removed from scope**;
2. links to the exact revised schematic/PCB/BOM/mechanical sources and immutable
   validation artifacts for every fixed item;
3. a current sourced-BOM report for Standard plus the intended Pro/Max scaling;
4. signed electrical and mechanical/thermal peer reviews;
5. a recorded owner statement that names the tiers released and the remaining
   prototype-only restrictions.

Passing a script alone does not release the program. Absence of a finding in a
later report also does not release it. The explicit owner decision is the final
gate.

## 5. Immediate recommended order of work

1. Freeze the exact resistor family and cartridge connector pair.
2. Correct and bench-validate one CC loop, including setpoint scaling and shunt.
3. Repartition the bank groups and protection around a quantified current limit.
4. Build and instrument the required resistor-wall sub-cartridge.
5. Assemble and validate a complete Tester Standard source project.
6. Recalculate and derive Pro/Max only from the released Standard cells.
