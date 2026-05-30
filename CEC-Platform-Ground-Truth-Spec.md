# CEC Platform: Ground-Truth Specification

**Status:** Working ground truth. This document holds precedence for the CEC platform. Where it conflicts with any earlier document, this document wins.

**Reconciles and supersedes:**
- *CEC Hub Standard v1.1 locked decisions* (Mini-Fit Jr connector): superseded on connector and cabling; all other v1.1 decisions carried forward.
- *Module sensing architecture v3* (RJ-45 connector strategy): adopted as the connector and communication basis.
- *Early CAN-FD / BOM thread* (JST-XH connector, i.MX 93 Enterprise): superseded.

**Last updated:** 2026-05-28
**Scope of this revision:** Full detail on the universal interface, Hub Standard, Hub Pro, and Pro modules. Enterprise and Mission Critical are summarized at platform level only (see OQ-7).

> Action item carried out of reconciliation: the Hub Standard and 12VHPWR schematics still show Mini-Fit Jr footprints and must be re-cut to RJ-45 before any board order. They are the stale artifacts, not this document.

---

## 1. Platform overview

The CEC platform is a modular PC power-telemetry system. Per-rail sensing modules connect to a central Hub over a single commodity cable. The Hub aggregates telemetry and forwards it to the host PC over USB. Four tiers are built from one fundamental design with progressively populated features:

| Tier | Role | Hub MCU | Host link | Distinguishing hardware |
|---|---|---|---|---|
| Standard | Mainstream builders | ESP32-S3 | USB Full Speed | CAN only, 4 ports |
| Pro | Overclockers, bench users | ESP32-P4 | USB High Speed | plus RS-485 streaming, 8 ports |
| Enterprise | Regulated / financial | ESP32-P4 | USB HS (plus optional 1000BASE-T1) | plus RJ-11 trust channel, secure element |
| Mission Critical | Defense, broadcast, render | ESP32-P4 plus crypto | Redundant uplinks | Redundant power, CAN, trust |

Modules are tier-agnostic: any module works in any Hub and degrades gracefully (see Section 7).

---

## 2. Universal physical interface

### 2.1 Connector (LOCKED)

- Module-to-Hub connector is **RJ-45 (8P8C)** for all tiers, all modules and Hubs. Mini-Fit Jr is retired platform-wide.
- **Locking-boot RJ-45 is the default** shipped in the box, chosen to remove the silent-dropout failure mode of a plain clip in a transported or vibrating chassis. Mechanical-keyed variants remain available for high-security deployments.
- Shielded jacks (FTP) on Hub and modules.

### 2.2 Pin allocation (LOCKED; two items pending)

| Pin | Cat5e pair | T568B color | CEC function | Tiers |
|---|---|---|---|---|
| 1 | Pair 1 | White-orange | VCC (+5VSB power) | All |
| 2 | Pair 1 | Orange | GND (power return) | All |
| 3 | Pair 3 | White-green | CAN1_H (control plus low-rate telemetry) | All |
| 4 | Pair 2 | Blue | STREAM_P (RS-485 data, module to Hub) | Pro+ |
| 5 | Pair 2 | White-blue | STREAM_N (RS-485 data, module to Hub) | Pro+ |
| 6 | Pair 3 | Green | CAN1_L | All |
| 7 | Pair 4 | White-brown | AUX_REF (precision reference) | Pro+, see OQ-3 |
| 8 | Pair 4 | Brown | DETECT / module-ID (analog single-wire sense) | All |

Notes:
- CAN runs classical at 500 kbps on Standard and CAN-FD on Pro and above, on the same pair.
- Pair 3 (pins 3 and 6) is the T568B split pair but stays twisted in the cable; standard practice for differential CAN.
- Standard tier leaves pair 2 unused, terminated at the module side.

### 2.3 DETECT / module-ID: analog single-wire sense (LOCKED as approach; encoding pending)

Pin 8 is an analog single-wire identity and presence sense. Each module carries a precision resistor from pin 8 to GND. The Hub reads pin 8 through a fixed pull-up to VCC, forming a divider, and converts it on an ADC channel.

- A valid resistor code means a module is present, and the code identifies module type and tier.
- An open line (reads near VCC) means no module.
- Proposed encoding: a table of E24 resistor values mapped to module-type and tier codes, with comfortable ADC margin between adjacent codes.

The exact code table is pending the final list of module types and tiers to encode (see OQ-6).

### 2.4 Cross-connect and PoE protection (LOCKED as requirement)

Because users may connect commodity Cat5e cables, every RJ-45 pin on every Hub and module carries over-voltage protection sized to survive accidental PoE injection (up to ~57V) and transients: a TVS array plus series limiting resistors.

Caution for layout: the series resistor on the VCC pin trades protection against voltage headroom on the 5VSB rail at the far end of a cable. Size it together with the power budget in Section 2.5, not independently.

### 2.5 Connector current rating and power budget (corrected; one item pending)

Correcting an earlier overstatement: a quality 8P8C contact carries roughly 1A continuously, and many connectors are rated 1.5A or higher, derated for cable bundling and temperature rise. This is consistent with how PoE works. PoE uses high voltage (roughly 48 to 57V) across multiple paralleled conductors, so even 90W Type-4 PoE puts well under 0.5A on any single conductor. CEC differs in two ways that matter:

1. It runs power at 5V, so it needs roughly ten times the current of 48V PoE for the same wattage.
2. The pinout uses a single VCC pin and a single GND pin, with no conductor paralleling.

Per-port current to a single module is comfortable (roughly 0.1 to 0.5A depending on LED state). The constraint is the trunk: the Hub draws its own current plus the current of every downstream module it powers, all through one VCC pin.

The worst-case driver is the SK6812 LED chain. Seven SK6812 at full white draw on the order of 0.4A per board. A Hub plus several downstream modules all at full-white LEDs can push the trunk toward 2A on a single pin, which exceeds a 1A contact and approaches the limit of a 1.5A contact. The 8-port Hub Pro makes this sharper than the 4-port Standard.

Required controls:
- Cap aggregate SK6812 current in firmware (global brightness or current budget) so the worst case stays within the chosen connector rating with margin.
- Select a connector with a documented rating of at least 1.5A.
- Resolve how the Hub receives bulk power (see OQ-1). If the Hub draws all downstream power through one module's RJ-45 VCC pin, the 8-port Pro is the binding case. A dedicated PSU power input on the Hub removes the constraint entirely.

### 2.6 Cable (mostly locked; lengths pending)

- Standard tier: quality Cat5e patch cable, FTP recommended near noisy GPUs.
- Pro and above with streaming active: Cat6 STP recommended for the RS-485 pair.
- CEC ships colored boots (bright orange) and labeled cables to differentiate from network cables.
- Cable length SKUs and the any-length versus fixed-length policy are pending (see OQ-4), because they interact with the precision-reference decision (OQ-3).

---

## 3. Communication architecture

### 3.1 CAN: control and low-rate telemetry (LOCKED)

- All control and command traffic lives entirely on CAN, on pair 3, for every tier.
- Classical CAN at 500 kbps on Standard; CAN-FD on Pro and above.
- Transceiver: TJA1462A (CAN-FD capable, run in classical mode on Standard).
- Termination: fixed 120 ohm split at the Hub.
- Bench item: star topology with up to 8 stubs at Pro CAN-FD rates should be signal-integrity verified. The risk is star termination plus stub length, rather than the bit rate itself.

### 3.2 RS-485: data streaming only (LOCKED; topology pending)

- RS-485 carries high-bandwidth telemetry streaming exclusively, one direction, module to Hub, on pair 2. It carries no control traffic.
- Present on Pro modules and Pro+ Hubs. Standard does not populate it.
- Lead case: 12VHPWR Pro streams about 900 kB/s, roughly 7 to 10 Mbps on the wire.
- Working basis: one RS-485 receiver per Hub port (point-to-point per port), which scales cleanly to the 8-port Pro. Confirm against a shared multidrop bus (see OQ-5).
- Bench item: verify rate margin and signal integrity at the maximum offered cable length before locking the streaming protocol. This is the classic case that passes on a 1m bench cable and fails on a 5m customer run.

### 3.3 AUX_REF: precision voltage reference (DECISION PENDING)

The platform goal is roughly +/- 0.15% rail-voltage accuracy via a 3.000V REF3033 reference and ratiometric correction at each module's ADC.

On the question of whether a fixed cable length makes the drop correctable: yes, for the DC term. At a fixed length, fixed gauge, and known reference-input current, the IR drop along the cable is a constant that can be calibrated out per cable-length SKU. Three caveats remain:

1. Calibrating per length locks Pro modules to characterized cable lengths, which is in tension with the RJ-45 any-length appeal. A user who swaps to an arbitrary length loses the calibration.
2. RJ-45 contact resistance drifts with insertion cycles, oxidation, and vibration, adding a small uncalibrated DC term on top of the cable drop.
3. The harder problem is AC. The reference is single-ended on one wire of pair 4, adjacent to the RS-485 streaming pair, so streaming edges couple onto it. That is an AC error rather than a fixed offset, so it cannot be calibrated out and must be filtered. Filtering it well means adding an RC plus buffer at each module.

Two viable paths, to be locked in OQ-3:

- **Path A, distributed and calibrated:** keep AUX_REF on pin 7, restrict Pro modules to characterized CEC cable lengths, keep reference-input current low and defined, add local RC filtering at each module, and calibrate the DC drop per length SKU.
- **Path B, local reference (recommended):** drop distributed AUX_REF and place a local REF3033 on each Pro module (about $1 to $2). Pro modules already carry an LTC2358-18 and precision analog parts, so a local reference fits and removes cable length, contact drift, and coupling from the accuracy budget at once. Pin 7 then frees up as a spare or for future use.

---

## 4. Hub Standard (LOCKED; connector updated)

All v1.1 decisions carry forward unchanged except connector and cabling.

| Item | Decision |
|---|---|
| Product name | CEC Hub Standard |
| Tier | 1 of 4 |
| Protocol | Classical CAN at 500 kbps over CAN-FD-capable transceiver |
| Topology | Star, 4 ports |
| Termination | Fixed 120 ohm split at Hub |
| Connector | 4x RJ-45 8P8C, locking boot (was Mini-Fit Jr 12-circuit) |
| Cable | Cat5e/6 (was custom Mini-Fit Jr); lengths per OQ-4 |
| MCU | ESP32-S3-MINI-1-N16R2 |
| CAN transceiver | TJA1462A |
| Regulator | LP5907 LDO |
| Hold-up | 4700 uF aluminum polymer bulk cap |
| Inrush limiting | 1 ohm 1 W series resistor |
| Reverse polarity | SS14 Schottky |
| Supervisor | TPS3839K33 with divider |
| Storage | ESP32-S3 internal flash, 16 MB (~10 MB available) |
| Identity | Factory MAC plus database mapping (no eFuse, no secure element) |
| LEDs | 7x SK6812 MINI-E RGB chain, with firmware current cap per Section 2.5 |
| LED control | Adalight via CDC plus CEC override priority |
| Service button | Hidden, GPIO0 (download mode) |
| Mounting | 4x M2.5 corner holes, chassis-grounded |
| PCB | 4-layer 1.6 mm, ENIG, matte black |
| Chassis | Plastic prototype; aluminum 6063 anodized production |
| Bulk power input | Inherited basis: from 24-pin module over RJ-45 VCC pin. Confirm per OQ-1. |
| Regulatory | Subassembly approach, no FCC cert for v1 |
| Production BOM | ~$36 (100-qty) |

---

## 5. Hub Pro (LOCKED on ports and MCU; shares Standard base)

| Item | Decision |
|---|---|
| Ports | 8x RJ-45 8P8C, locking boot |
| MCU | ESP32-P4 (USB HS resolves the streaming bandwidth ceiling) |
| Protocol | CAN-FD on the control pair, plus RS-485 streaming receivers |
| Streaming receivers | One RS-485 receiver per port (working basis, OQ-5) |
| Host link | USB High Speed |
| Reference | REF3033 source only if Path A is chosen in OQ-3 |
| Bulk power input | Binding case for OQ-1: 8 downstream modules through one VCC pin is the limiting current path |
| Production BOM | ~$45 (100-qty) |

Everything else (regulator, hold-up, supervisor, LEDs, PCB approach, identity) follows the Hub Standard base unless changed by a future revision.

---

## 6. Pro module (lead: 12VHPWR Pro)

| Item | Decision |
|---|---|
| MCU | ESP32-P4 |
| Per-pin current sensing | INA240A3 analog current-sense amps on per-pin shunts |
| ADC | LTC2358-18, 8-channel simultaneous-sampling 18-bit SAR (sub-millisecond inter-pin timing) |
| Rail voltage | 47k/10k divider into one LTC2358 channel |
| Streaming | ~50 kHz x 6 channels, about 900 kB/s, over RS-485 (pair 2), module to Hub |
| Control | CAN-FD (pair 3) |
| Reference | Per OQ-3 (local REF3033 recommended) |
| Connector | RJ-45 8P8C, locking boot |
| Production BOM | ~$98 to $99 (100-qty) |

Cross-tier note: a Pro module in a Standard Hub runs CAN control and event telemetry normally; its streaming pair is connected at the jack but stays dark because the Standard Hub does not populate an RS-485 receiver. This is the intended graceful-degrade behavior.

---

## 7. Cross-tier compatibility

| Module \ Hub | Standard Hub | Pro Hub | Enterprise Hub | Mission Critical Hub |
|---|---|---|---|---|
| Standard module | Native | Works, Hub oversupplied | Works | Works, module is the weak link |
| Pro module | Works, streaming dark | Native | Native | Works |

Principle: a module never fails to function in any Hub. Higher-tier features go dormant when the Hub cannot service them, and activate without module replacement when moved to a capable Hub.

---

## 8. BOM summary (production, 100-qty)

| Item | BOM | Tier |
|---|---|---|
| 24-pin ATX module | $35 | Standard |
| EPS 8-pin module | $32 | Standard |
| PCIe 8-pin module | $38 | Standard |
| 12VHPWR Standard module | $49 | Standard |
| 12VHPWR Pro module | $98 to $99 | Pro |
| Hub Standard | $36 | Standard |
| Hub Pro | $45 | Pro |
| Hub Enterprise | $50 | Enterprise |
| Hub Mission Critical | $80 | Mission Critical |

---

## 9. Open questions (decisions needed; no assumptions made)

**OQ-1: Hub bulk power input (critical).** Does the Hub, especially the 8-port Pro, receive bulk power from the 24-pin module over a single RJ-45 VCC pin, or from a dedicated PSU power input (for example SATA or peripheral power)? This decides whether the single-pin trunk current in Section 2.5 is a real constraint. Recommendation: a dedicated power input on the Pro Hub at minimum.

**OQ-2: LED current cap.** Confirm a firmware cap on aggregate SK6812 current, and the maximum LED state to budget for. Needed to size the trunk and the connector rating.

**OQ-3: Precision reference path.** Lock Path A (distributed AUX_REF, calibrated per cable length, with local filtering) or Path B (local REF3033 per Pro module). Recommendation: Path B.

**OQ-4: Cable length SKUs and policy.** What fixed cable lengths will be offered, and are Pro modules allowed on arbitrary user cables (accepting reduced reference accuracy under Path A) or restricted to characterized CEC cables? Interacts with OQ-3.

**OQ-5: RS-485 topology.** Confirm one receiver per Hub port (point-to-point) versus a shared multidrop bus across ports.

**OQ-6: Module-ID encoding.** Provide the full list of module types and tiers that need distinct analog ID codes so the resistor table in Section 2.3 can be finalized.

**OQ-7: Document scope.** Should this document fully specify Enterprise and Mission Critical now, or keep them at platform-summary level until their first customer requirements land?

---

## 10. Revision history

- **This document:** established as platform ground truth. RJ-45 8P8C locked across Standard and Pro with locking boot; Mini-Fit Jr retired; DETECT defined as analog single-wire ID and presence sense; Hub Pro fixed at 8 ports; control confirmed entirely on CAN with RS-485 for streaming only; connector current understanding corrected; precision-reference and bulk-power decisions opened for resolution.
- **Prior:** v1.1 Hub Standard (Mini-Fit Jr) and v3 architecture (RJ-45) reconciled here.
