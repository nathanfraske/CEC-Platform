# CEC Standard tier: proof state (2026-07-06)

For Chris. Exactly what exists now, what is proven and how, and what is still owed.
Grounded in the repo, not the marketing framing. The point of this doc is the honest
line between "proven in the design tools" and "proven on real hardware," because those
are very different levels of confidence and the difference is where the remaining work is.

## How to read this

Four states, used consistently below:

- **Showable now**: a physical object, a manufacturing-ready gerber set, a render, or a
  tool you can run in front of someone today.
- **Proven in CAD / simulation**: verified by DRC, ERC, netlist export, the geometry
  checker, a test suite, or a solver that is calibrated to a real external datum. This is
  real evidence. It is not the physical product measured under load.
- **Proven on hardware (bench)**: measured on a real board. This bucket is thin today, and
  that is the honest headline: most of what we have is proven in the design tools and
  against reference data, not yet on instrumented hardware.
- **Owed**: the specific gate that closes it.

## 1. What physically exists and can be shown today

- **Two fab-ready boards, manufacturing files generated.** Hub Standard and 12VHPWR Standard
  are fully routed, DRC ERROR-clean, out of DRAFT, with committed gerbers, BOM, and pick-and-place
  files under `fab/hub-standard-proto-v1/` and `fab/12vhpwr-standard-proto-v1/`. These can go to
  a board house as-is. (Hub Standard 769 tracks / 137 vias / 51 zones; 12VHPWR 1182 / 413 / 37.)
- **Physical alpha prototypes of the Standard line.** Working prototypes of the consumer boards
  exist and validated the concept. This is the "alpha, validated" claim. (Owner-attested; the
  physical boards are not something the repo can prove on its own.)
- **The full board set in CAD.** Every board in the platform exists as a schematic and a
  placed PCB: the 24-pin (alpha + rev2 + rev3), EPS, both PCIe SKUs, the three output
  daughterboards, the ARGB Standard controller, and the ENT KVM carrier.
- **Renders, thermal maps, connector fit drawings, sourced BOMs.** All demonstrable artifacts.
- **The design and verification toolchain.** A deterministic router, an electrothermal solver
  calibrated to a manufacturer datum, a 166-test thermal suite, a golden regression, and a
  geometry checker with 113 assertions. Runnable live.

## 2. Proven and tested: theory vs practice

| Capability | In theory (designed / spec'd) | Proven in CAD / simulation | Proven on hardware (bench) | Evidence |
|---|---|---|---|---|
| Per-rail voltage / current / power sensing (24-pin 4x INA238, EPS/PCIe per-cable) | Yes, spec 6.1 | Schematic + netlist verified; parts datasheet-pin-audited | No | gen-modules, netlist exports, symbol audit |
| Per-pin 12V current, the melt detector (12VHPWR 6x INA240) | Yes, spec 6.1 | Yes, on the routed fab-ready board | No, not measured under real GPU load | 12vhpwr routed PCB + fab snapshot |
| Sensing accuracy | Yes (target +/-0.3 to 0.5% on 12VHPWR) | Calculated: RSS ~0.50% at 600W from shunt-TCR + amp/ref drift models | No, not measured | `cec_thermal_accuracy.py` |
| Two boards manufacturable | Yes | Yes, DRC ERROR-clean, gerbers generated | Boards not yet fabbed from these exact files | `fab/` snapshots, CI DRC gate |
| Thermal survival of the copper | Yes, spec 6.4/6.7 | Yes: analytic IPC + 2.5D FEM, calibrated to TE's 22.9A -> 30C rating datum, teeth-tested; daughterboard F1 fix DC-IR-proven (+5V 384 -> 62.6 mV) | No, no thermal soak on hardware | `blade-interconnect-thermal-2026-07-06.md`, thermal-maps/ |
| Connector joint current rating | Yes, ratified 22.9A/125%, counts 10/6/6 | Margins computed; joint element calibrated to the datum | No, physical fit and contact-R not measured | joint solver, fit-check memo |
| Connector keying (a family can't seat in the wrong board) | Yes | Yes, proven mathematically: no rigid transform seats one family as a subset of another, teeth-tested | No, not physically mated | `check_output_daughterboards.py` |
| Communication (CAN 500 kbps) | Yes, spec 3.1 | Transceiver part rated and placed; netlist verified | No, no bus signal-integrity bench | TJA1051T/3 selection, schematics |
| Protection posture (ESD on DETECT, USB, standalone) | Yes, spec 2.4/6.14 | On the schematics / library | No | gen-modules, lib |
| The design toolchain itself | Yes | Yes, 166 thermal tests + golden regression + 113 checker assertions all pass | Runs on real KiCad 10 in CI | `tests/`, `tests/golden/` |

The pattern: the middle column is well-populated, the right column is nearly empty. We have
strong CAD and simulation evidence, calibrated where possible to real manufacturer data. We do
not yet have the product measured on a bench under load.

## 3. What still needs to be proven

**The one physical hardware gate that unlocks the connector architecture (OQ-86):**
- A sample order and physical fit-check: does the TE 63951-1 blade seat in the TE 63969-1
  receptacle at the designed float. Specific unknowns: the receptacle's un-dimensioned
  across-thickness depth (drawn ~3.7 mm; over 4.0 mm forces the atx24 board to a wider pitch),
  gang insertion force at 10 to 18 joints, and detent engagement at the nominal float.
- A thermal soak on a mated joint, which is the decisive datum for the daughterboard
  board-level thermal (F2) question. The model gives specific numbers to check against:
  17.3A -> ~17C, 22.9A -> ~30C, and a contact-resistance spread threshold (atx24 GND at
  spread ratio ~0.21, EPS ~0.28) as the bench acceptance criteria.

**Firmware, essentially all of it.** The sensing hardware is designed and, on two boards, built,
but the logic that turns readings into a product is spec'd and not written: the acquisition
engine (1 kHz ring buffer + threshold freeze), the per-pin imbalance alert, energy integration,
cross-module synchronized capture, persist-on-fault flush, the OS-native HID sensor descriptors,
standalone mode, and single-point firmware update. An earlier firmware effort (PR #50) covers a
USB serial path and a capture CLI; it is not the acquisition and alerting product.

**Product accuracy on the bench.** The 0.5% figure is calculated from component tolerance and
drift models. It has not been measured against a reference meter on a real board.

**The daughterboard board-level thermal envelope (F2).** The joint passes and the copper no
longer fuses, but the small still-air, no-sink worst-case still models hot. Closing this needs
the OQ-86 soak plus either a modelled-and-verified conduction sink, heavier inner copper, or an
owner-accepted operating-envelope statement. The 30C gate was not relaxed to hide this.

**EMC / regulatory.** The unintentional-radiator, no-Wi-Fi posture is a design decision, not a
tested or certified result.

**Board work to reach fab on the beta line.** EPS, PCIe 2-port, and PCIe 3-port are placed with
zero copper routed. The three output daughterboards are routed and DRC-clean but DRAFT and not
fabbed. The 24-pin rev3 (INA238) and the C6-MCU refresh are in CAD, not fabbed.

**Bus signal integrity at the optional 1 Mbps.** 500 kbps is the locked floor and is fine. The
1 Mbps option rests entirely on a bench signal-integrity test that has not been run.

## One-paragraph summary for Chris

The concept is validated on physical prototypes, and two boards (Hub Standard, 12VHPWR Standard)
are manufacturing-ready with gerbers in hand. The sensing, thermal, and connector engineering is
proven in the design tools and calibrated to real manufacturer data, which is solid evidence but
is not the same as the product measured on a bench. The owed work, in order of impact, is: the
OQ-86 connector fit-check and thermal soak (one sample order), the acquisition-and-alerting
firmware (spec'd, unwritten), a bench accuracy measurement, and routing plus fab of the rest of
the beta line. Nothing in this doc is claimed as hardware-proven that is only simulated.
