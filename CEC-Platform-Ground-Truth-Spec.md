# CEC Platform: Ground-Truth Specification

**Status:** Controlled baseline. This document is the single source of truth for the CEC platform and holds precedence over every earlier document. All future decisions are versioned here. Where any earlier document conflicts, this document wins.

**Document version:** 1.8

**Reconciles and supersedes:**
- *CEC Hub Standard v1.1 locked decisions* (Mini-Fit Jr connector): superseded on connector and cabling; all other v1.1 decisions carried forward.
- *Module sensing architecture v3* (RJ-45 connector strategy): adopted as the connector and communication basis.
- *Module sensing architecture v4* (INA238/INA228 sensor selection): current-sensing adopted; superseded on precision-reference distribution, DETECT definition, pin-7 allocation, and 24-pin shunt values, which this document overrides.
- *Early CAN-FD / BOM thread* (JST-XH connector, i.MX 93 Enterprise): superseded.
- *CEC PCB-repo ground-truth spec* (GitHub, 2026-05-30): reconciled here. Its Standard-module MCU lock is adopted; its 24-pin sensor, 12VHPWR Standard sensing, and platform-wide PoE drop diverge from this document and are addressed in Section 2.4, Section 6.1, and OQ-14.

**Last updated:** 2026-06-02
**Scope of this revision:** Full detail on the universal interface, Hub Standard, Hub Pro, and the module sensing and current-handling domain including the Pro module. Enterprise and Mission Critical are summarized at platform level only (see OQ-7). v1.6 adds the module PSU-side power-path connector and interposer-cabling rules (Section 2.8). v1.7 finalizes the DETECT module-ID code table (Section 2.3, resolving OQ-6) and records the shielded-jack divergence (OQ-15). v1.8 moves the Hub Standard MCU to the ESP32-S3-WROOM-1-N16R8 (the MINI-1-N16R2 named in earlier revisions is not a real SKU).

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

Standard-tier modules (24-pin ATX, EPS 8-pin, PCIe 8-pin, 12VHPWR Standard) run the **ESP32-S3-MINI-1** (LOCKED, v1.5; adopted from the PCB repo). The Hub Standard uses the same ESP32-S3 family in the larger **ESP32-S3-WROOM-1-N16R8** module (16 MB flash + 8 MB PSRAM) for the aggregation role (v1.8); the MINI-1 form factor tops out at 8 MB flash and has no 16 MB SKU. The 12VHPWR Pro module runs the ESP32-P4 (Section 6.9).

---

## 2. Universal physical interface

### 2.1 Connector (LOCKED)

- Module-to-Hub connector is **RJ-45 (8P8C)** for all tiers, all modules and Hubs. Mini-Fit Jr is retired platform-wide.
- **Locking-boot RJ-45 is the default** shipped in the box, chosen to remove the silent-dropout failure mode of a plain clip in a transported or vibrating chassis. Mechanical-keyed variants remain available for high-security deployments.
- Shielded jacks (FTP) on Hub and modules.

Implementation divergence (open, OQ-15): current boards place the unshielded Amphenol 54602 with grounded SH1/SH2 board-locks rather than a metal-shell FTP jack. This is acceptable for prototype bring-up — the module link carries only CAN, 5VSB, DETECT, and the (Standard-dark) RS-485 pair, all shielding-insensitive at these rates — but the FTP requirement stands for production and EMC. See OQ-15.

### 2.2 Pin allocation (LOCKED; two items pending)

| Pin | Cat5e pair | T568B color | CEC function | Tiers |
|---|---|---|---|---|
| 1 | Pair 1 | White-orange | VCC (+5VSB power) | All |
| 2 | Pair 1 | Orange | GND (power return) | All |
| 3 | Pair 3 | White-green | CAN1_H (control plus low-rate telemetry) | All |
| 4 | Pair 2 | Blue | STREAM_P (RS-485 data, module to Hub) | Pro+ |
| 5 | Pair 2 | White-blue | STREAM_N (RS-485 data, module to Hub) | Pro+ |
| 6 | Pair 3 | Green | CAN1_L | All |
| 7 | Pair 4 | White-brown | Reserved spare (no distributed reference; see Section 3.3) | All |
| 8 | Pair 4 | Brown | DETECT / module-ID (analog single-wire sense) | All |

Notes:
- CAN runs classical at 500 kbps on Standard and CAN-FD on Pro and above, on the same pair.
- Pair 3 (pins 3 and 6) is the T568B split pair but stays twisted in the cable; standard practice for differential CAN.
- Standard tier leaves pair 2 unused, terminated at the module side.

### 2.3 DETECT / module-ID: analog single-wire sense (LOCKED as approach; encoding pending)

Pin 8 is an analog single-wire identity and presence sense. Each module carries a precision resistor from pin 8 to GND. The Hub reads pin 8 through a fixed **10 kΩ pull-up to its 3.3 V ADC reference**, forming a divider, and converts it on an ADC channel. (The pull-up goes to the Hub's 3.3 V logic/ADC reference, not the 5VSB VCC pin: a 5VSB pull-up would drive the ESP32 ADC input above its range. This refines the earlier "pull-up to VCC" wording — the chart below only resolves on 3.3 V.)

- A valid resistor code means a module is present, and the code identifies the module's **link capability**, which tells the Hub which receivers and PHYs to bring up.
- An open line (reads near 3.3 V) means no module; a shorted line (0 V) flags a bridged or damaged cable.

**DETECT code table (LOCKED, v1.7; resolves OQ-6).** E24 resistor from pin 8 to GND, read on the 10 kΩ / 3.3 V divider:

| Code | Resistor | V at pin 8 | Hub action |
|---|---|---|---|
| CAN-only | 2.2 kΩ | 0.595 V | no streaming receiver |
| CAN + RS-485 | 4.7 kΩ | 1.055 V | enable RS-485 receiver |
| CAN + 100BASE-T1 | 10 kΩ | 1.650 V | bring up 100BASE-T1 PHY (per OQ-20) |
| Reserved A | 22 kΩ | 2.269 V | future link |
| Reserved B | 47 kΩ | 2.721 V | future link |
| No module | open | ~3.3 V | empty or broken cable |
| Fault | short | 0 V | bridge or damaged cable |

The encoding is by **link capability** (what the module can talk), which is exactly what the Hub needs to decide which receivers and PHYs to activate; module type and tier ride on CAN once the link is up. Codes are spaced for comfortable ADC margin (about 0.45 V or more between adjacent codes). The 100BASE-T1 row references the Enterprise link question (OQ-20), not yet opened in Section 9 while Enterprise stays at platform-summary level (OQ-7). The 24-pin, EPS, PCIe, and 12VHPWR Standard modules are all CAN-only (2.2 kΩ); 12VHPWR Pro is CAN + RS-485 (4.7 kΩ).

### 2.4 Cross-connect and PoE protection (requirement; implementation divergence open, OQ-14)

Because users may connect commodity Cat5e cables, every RJ-45 pin on every Hub and module carries over-voltage protection sized to survive accidental PoE injection (up to ~57V) and transients: a TVS array plus series limiting resistors.

Caution for layout: the series resistor on the VCC pin trades protection against voltage headroom on the 5VSB rail at the far end of a cable. Size it together with the power budget in Section 2.5, not independently.

Implementation divergence (open, OQ-14): the PCB repo as of 2026-05-30 does not populate this protection on Standard or Pro boards, treating consumer cross-connect as out of scope and keeping the question only for Enterprise and Mission Critical. That reverses this locked requirement and is already reflected in current boards. With bulk power moved off the RJ-45 (Section 2.7), an accidental 57V cross-connect still reaches the RJ-45 signal pins and the 5VSB-out pin with nothing to clamp it, so the requirement stands in this document until the divergence is ratified or reversed. The board state is not the decision. See OQ-14.

### 2.5 Connector current rating and power budget (corrected; bulk power resolved v1.3)

Correcting an earlier overstatement: a quality 8P8C contact carries roughly 1A continuously, and many connectors are rated 1.5A or higher, derated for cable bundling and temperature rise. This is consistent with how PoE works. PoE uses high voltage (roughly 48 to 57V) across multiple paralleled conductors, so even 90W Type-4 PoE puts well under 0.5A on any single conductor. CEC differs in two ways: it runs power at 5V (so roughly ten times the current of 48V PoE for the same wattage), and each RJ-45 carries a single VCC and a single GND pin with no paralleling.

Bulk power resolution (OQ-1): the Hub does not draw aggregate power through an RJ-45 VCC pin. The 24-pin module feeds the Hub over a dedicated 2-pin JST-XH 5VSB cable, and the Hub distributes 5VSB to each downstream module over that module's own RJ-45 VCC pin. So each RJ-45 VCC pin carries one module's draw only (roughly 0.1 to 0.5A depending on LED state), comfortably inside the contact rating. The aggregate now lives on the JST-XH feed and, upstream of it, the PSU 5VSB rail.

That leaves two shared limits, both in the 3A class: the JST-XH contacts and the PSU 5VSB rail, which CEC shares with the motherboard's own standby load. The dominant variable is the SK6812 LED chains. Seven SK6812 at full white draw on the order of 0.4A per board, so a fully populated Hub plus modules at full-white LEDs can push total 5VSB draw past 3A, exceeding both the JST-XH rating and the rail. The firmware current cap (OQ-2) therefore governs total 5VSB draw, not only the LEDs.

Required controls:
- Cap total CEC 5VSB current in firmware (the LED budget is the main lever) so the worst case stays within the JST-XH rating and the shared 5VSB budget with margin. Size against a ~2.5A rail to cover weaker PSUs and the motherboard's own standby draw. See OQ-2.
- RJ-45 per-module VCC pins: a connector rated 1.5A or higher is ample, since each carries one module.
- JST-XH bulk feed: confirm its contact rating covers the capped aggregate with margin (XH is ~3A class; a heavier series is available if more headroom is wanted than the cap provides).

The Hub-side bulk-power connector, its keying, and where it lands on the Hub front end are specified in Section 2.7.

### 2.6 Cable (mostly locked; lengths pending)

- Standard tier: quality Cat5e patch cable, FTP recommended near noisy GPUs.
- Pro and above with streaming active: Cat6 STP recommended for the RS-485 pair.
- CEC ships colored boots (bright orange) and labeled cables to differentiate from network cables.
- Cable length SKUs and the any-length versus fixed-length policy are pending (see OQ-4), because they interact with the precision-reference decision (OQ-3).

### 2.7 Hub bulk power input (LOCKED; resolves OQ-1)

The Hub receives bulk power on a dedicated 2-pin power-in connector, separate from the RJ-45 interface, carrying +5VSB into the Hub from the 24-pin ATX module (which taps 5VSB at the PSU's 24-pin connector). The Hub distributes that 5VSB outward to each port over the RJ-45 VCC pin. This holds for every Hub and removes the single-VCC-pin trunk constraint of Section 2.5: aggregate current no longer passes through any one RJ-45 contact, so the 8-port Pro is no longer the limiting case.

The connector architecture is locked; the specific part is the simplest one meeting the rating and is a working selection rather than itself locked:
- 2-pin, polarized and keyed against reverse insertion. Working selection: 2-pin JST-XH (~3A class). It is distinct from the retired Mini-Fit Jr and from the superseded JST-XH interface use; here it is a power-only feed. Step up to a higher-current 2-pin part (for example JST-VH) if the capped trunk budget grows.
- Documented rating at or above the capped aggregate with margin.
- Lands on the Hub's existing 5VSB front end: SS14 reverse-polarity Schottky, 1 ohm 1 W inrush limiter, 4700 uF hold-up, TPS3839K33 supervisor. As an internal PC power lead it is not exposed to the commodity-cable cross-connect threat of Section 2.4, so it carries no per-pin over-voltage network; reverse-polarity and inrush protection still apply.

### 2.8 Module power-path connectors (PSU side) — interposer cabling (LOCKED, v1.6)

Separate from the universal RJ-45 module-to-Hub interface (Sections 2.1 to 2.7), each sensing module is a power-path interposer: PSU rail current enters the module, passes through its shunts, and continues to the load. The PSU-side connectors are module-specific (not universal) and are locked per module as follows.

**24-pin ATX module — two male headers; female-to-female output cable required.** Gender convention for this spec: the board-mounted headers are **male** (pin-side), and a cable end that plugs onto a header is **female** (socket/receptacle) — so the PSU's own 24-pin cable is the female inserting connector. The module carries two Molex Mini-Fit Jr (5569 family) 24-circuit **male headers**: one on the PSU side (input, J3) and one on the motherboard side (output, J4). No board-mount **female** 24-pin ATX receptacle exists as a standard part, so the module cannot present a female socket on either side; both connectors are therefore male, the same gender as the motherboard's own 24-pin header.
- Input: the PSU's existing 24-pin cable (a female receptacle housing) plugs directly onto the module input header. No new cable is needed here.
- Output: the motherboard's 24-pin connector is also a male header, so the module output (male) and the motherboard (male) cannot be joined by an ordinary PSU-style cable, which is female on only one end. The run from the module output to the motherboard requires a dedicated **female-to-female 24-pin ATX bridging cable** — a female receptacle on each end, since each end plugs onto a male header (the module output and the motherboard). No standard off-the-shelf product carries a female on both ends, so CEC must supply this cable as a platform SKU.

**12VHPWR modules (Standard and Pro) — connectors soldered to the board.** The 12VHPWR module does not use detachable pass-through headers and does not need a bridging cable. Its 12VHPWR (12V-2x6) connector(s) are soldered directly to the module PCB (board-mounted). On the platform's highest-current, melt-prone connector this removes a mated-contact pair from the power path and keeps the connection deterministic.

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

### 3.3 Precision voltage reference (RESOLVED, v1.1)

The platform goal is roughly +/- 0.15% rail-voltage accuracy via a 3.000V REF3033 and ratiometric correction.

**Decision: local reference on each Pro module. No distributed reference. Pin 7 is a reserved spare.**

Each Pro module carries its own REF3033 (about $1 to $2) feeding ratiometric correction at the LTC2358-18. Distribution over the cable was rejected for three reasons: calibrating the DC cable drop ties Pro modules to characterized lengths and fights the RJ-45 any-length appeal; RJ-45 contact resistance drifts with insertion cycles and vibration; and the reference would run single-ended on pair 4 next to the RS-485 streaming pair, so streaming edges couple onto it as an AC error that cannot be calibrated out, only filtered.

The sensor line settles this further. The 24-pin, EPS, and PCIe modules sense with the INA238 (see Section 6), which carries its own internal reference and has no external-reference input, so it can neither use nor needs a distributed reference, and it is already tight (around +/- 0.1% typ). The only Standard module on a raw ADC is the 12VHPWR Standard (INA240 into the ESP32-S3 ADC); if it needs tighter accuracy, a local reference on that one board beats distribution (see OQ-8).

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
| MCU | ESP32-S3-WROOM-1-N16R8 (16 MB flash, 8 MB PSRAM; PCB-antenna keepout honored for a future Wi-Fi option) |
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
| Bulk power input | Dedicated 2-pin JST-XH 5VSB feed from the 24-pin module (OQ-1 resolved); 5VSB distributed to downstream modules over their RJ-45 VCC pins |
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
| Reference | None (Pro modules carry local REF3033 references) |
| Bulk power input | Dedicated 2-pin JST-XH 5VSB feed from the 24-pin module (OQ-1 resolved); the 8-port aggregate sits on the JST-XH feed and the shared 5VSB rail, bounded by the OQ-2 current cap |
| Production BOM | ~$45 (100-qty) |

Everything else (regulator, hold-up, supervisor, LEDs, PCB approach, identity) follows the Hub Standard base unless changed by a future revision.

---

## 6. Module sensing and current handling (production)

This section covers the module-internal sensing domain: how each module measures the motherboard power flowing through its shunts on the way to the board, and how that high current is handled on the PCB. These currents, tens of amps of monitored rail current, are a separate domain from the RJ-45 trunk current in Section 2.5. Section 2.5 is the 5VSB that powers the module's own electronics; the currents here are the monitored load, which flows through external shunts rather than through the sense silicon (which stays cool).

### 6.1 Production current-sensing summary

| Module | Tier | Current sensing | Voltage sensing | Streaming | Reference |
|---|---|---|---|---|---|
| 24-pin ATX | Standard | 4x INA228 (one per rail) | INA228 bus register (20-bit, 195 µV LSB) | none | INA228 internal |
| EPS 8-pin | Standard | INA238, one per cable (1 to 2) | INA238 bus register | none | INA238 internal |
| PCIe 8-pin | Standard | INA238, one per position (up to 3) | INA238 bus register | none | INA238 internal |
| 12VHPWR Standard | Standard | INA240 per pin into ESP32-S3 ADC | 47k/10k divider into ESP32-S3 ADC | none | see OQ-8 |
| 12VHPWR Pro | Pro | INA240 per pin into LTC2358-18 | 47k/10k divider into LTC2358-18 | RS-485 (pair 2) | local REF3033 |

The 24-pin uses the INA228 on all four rails (12V, 5V, 3.3V, 5VSB): 20-bit, 195 µV bus-voltage LSB, with hardware energy and charge accumulators. EPS and PCIe use the INA238: 16-bit, 3.125 mV bus-voltage LSB, no accumulators. Both share the same shunt scheme and the same 50 us minimum conversion (~20 kHz per-sensor ceiling), which clears the 10 kHz burst target.

The split is by limiting error source. The 24-pin's deliverable is fine voltage, which is ADC-limited, so it gets the INA228. EPS and PCIe deliver per-cable current totals, which are shunt-limited, so the INA238 is right-sized and its lower resolution and gain accuracy sit below the shunt floor anyway (Section 6.5). INA228 is used on all four 24-pin rails rather than only the 12V droop rail for two reasons: voltage resolution matters more on the 24-pin than anywhere else in the system, and droop on the 5V, 3.3V, and 5VSB rails is not yet characterized, so keeping 195 µV resolution on every 24-pin rail lets us detect and read that droop if it exists rather than designing it out. The accumulators come along on every 24-pin rail as a result, including complete 5VSB standby energy (energy scope is OQ-13).

The digital-sensor modules are self-referenced; only the 12VHPWR modules use a separate reference path, resolved locally on Pro (Section 3.3).

### 6.2 Sensing granularity policy (LOCKED, v1.2)

Granularity is set per connector type, drawn at the level that matters for that connector:

- **24-pin:** one shunt per rail (12V, 5V, 3.3V, 5VSB), each carrying that rail's combined pins. One cable, four rails.
- **EPS and PCIe:** per cable. Each cable's 12V pins bundle to a node and its grounds to a node on the PCB, and that cable's 12V is sensed through its own shunt, one monitor per cable. A module carries one such path per cable (two on EPS, up to three on PCIe). Total device current is the sum of the per-cable readings.
- **12VHPWR:** per pin, six INA240A3 on six per-pin shunts. This is the connector where per-pin current imbalance is the actual failure mode (the melting issue), so per-pin hotspot visibility is kept where it matters.

Stated limitation: per-cable sensing catches cable-level imbalance (a hogging or near-dead cable) but not per-pin imbalance within a single cable. That residual is accepted on EPS and PCIe because their pins carry real margin, while 12VHPWR keeps full per-pin coverage. The EPS 2x INA238 and PCIe 3x INA238 counts in Section 6.1 and the BOM are correct as one monitor per cable.

### 6.3 Module current targets (LOCKED, v1.2)

Policy: size every current path to the connector's real over-spec ceiling plus transient headroom, not its nameplate rating. Real cables and loads routinely exceed the official spec, and the tool must not saturate or become the bottleneck.

| Connector / rail | 12V pins | Nameplate | Design sustained | Transient to survive |
|---|---|---|---|---|
| 24-pin 5V | 4 to 5 | varies | 20A | mild |
| 24-pin 3.3V | 3 to 4 | varies | 20A | mild |
| 24-pin 12V | 2 | ~150 to 190W | ~15A (2-pin limited) | mild |
| 24-pin 5VSB | 1 | low | ~3A | mild |
| EPS 8-pin, per cable | 4 | ~350 to 380W | ~55A | ~75A |
| PCIe 8-pin, per cable | 3 | 150W | ~36 to 40A | ~60 to 75A |
| 12VHPWR, per pin | 6 | 600W / 50A | ~9.5 to 12A per pin | per-pin |

The EPS and PCIe figures are per cable, sized for the single-cable worst case since cables do not split load evenly, and replicated once per cable. EPS and GPU rails spike 1.5 to 2x sustained for milliseconds, so the shunt and copper must survive the transient column even though the sustained number sets the thermal design. This table is the sizing input for shunts, copper, vias, and thermal across every module.

### 6.4 Shunt selection (LOCKED values, v1.2; parts PENDING per OQ-11)

Sized so max current plus transient stays inside the ADC range and dissipation stays manageable:

| Module / rail | Shunt | Drop / power at max | ADC range | LSB | Full scale |
|---|---|---|---|---|---|
| 24-pin 12V, 5V, 3.3V | 2 mΩ | up to 40 mV / 0.8 W at 20A | +/-163.84 mV | 156 µA (INA228) | 81.9A |
| 24-pin 5VSB | 25 mΩ | 75 mV / 0.23 W at 3A | +/-163.84 mV | 12.5 µA (INA228) | 6.55A |
| EPS, per cable | 0.5 mΩ | 27 mV / 1.5 W at 55A | +/-40.96 mV | 2.5 mA (INA238) | 81.9A |
| PCIe, per cable | 0.5 mΩ | 20 mV / 0.8 W at 40A | +/-40.96 mV | 2.5 mA (INA238) | 81.9A |
| 12VHPWR, per pin | 1 mΩ | 12 mV / 0.14 W per pin | INA240A3 analog | ADC-set | per-pin |

The EPS and PCIe rows are one shunt per cable, identical and replicated across the module's cables. 24-pin 12V is 2-pin-limited to ~15A and may instead use the +/-40.96 mV range for finer resolution (about 39 µA per count on the INA228) if confirmed never to approach 20A. LSB shown is for the resident part (INA228 on the 24-pin, INA238 on EPS/PCIe); full scale is set by shunt and range and is identical across parts.

Shunt type: low-TCR metal-element / manganin precision shunt (<= 15 to 25 ppm/°C), tight tolerance, power rating well above the dissipation above (2 to 3 W parts for sub-1.5 W actual). Self-heating times TCR is the dominant thermal-accuracy error, and at 0.5 mΩ a few µΩ of tolerance or drift is a large fraction of the value, so the precision shunt is what protects accuracy at the low end. This supersedes the earlier v4 24-pin 5V and 3.3V values (which saturate the ADC above ~8A and ~3.3A and dissipate too much at 20A).

### 6.5 Resolution and ADC range (characterized, v1.2)

The range bit (ADCRANGE) recovers the resolution a low shunt would otherwise cost. A 0.5 mΩ shunt on the +/-40.96 mV range gives 2.5 mA per count and 81.9A full scale, identical to a 2 mΩ shunt on the +/-163.84 mV range. Every high-current channel lands on the same 2.5 mA resolution and ~82A full scale regardless of shunt value.

The low shunt's only cost is an accuracy floor at the bottom of the range, not a resolution limit. Input offset and noise are fixed voltages, so at 0.5 mΩ a ~5 µV offset maps to about 10 mA of error versus ~2.5 mA at 2 mΩ. That floor is 0.02% at 50A and reaches ~1% only near 1A, below where these rails operate and below the rail's own ripple. Gain error is a percentage of reading and does not move with shunt value. Record the per-channel ADCRANGE setting; 16-bit (INA238) or 20-bit (INA228) plus range selection covers all rails with headroom.

The 24-pin adds a resolution axis the high-current rails do not need: bus-voltage resolution for droop. The INA228 there resolves bus voltage at 195 µV per count against the INA238's 3.125 mV, which is the difference between resolving roughly 12 W and roughly 200 W of load change through the 12V cross-regulation coefficient (about 16 µV/W). The 24-pin carries the 20-bit part for that voltage axis rather than for current resolution; finer current (about 156 µA per count at 2 mΩ) comes along as a side effect.

### 6.6 Thermal design (LOCKED, v1.2)

No discrete or finned heatsinks.

- The INA238 dissipates about 2 mW. Load current bypasses the chip through the external shunt, so the monitor never needs cooling.
- The shunt dissipates 0.2 to 1.5 W depending on rail and value. Its heatsink is the PCB copper: the same wide 2 oz pour that carries the current, plus thermal vias around the shunt pads.
- The anodized 6063 aluminum production chassis is the heat spreader. Couple the high-current copper to the chassis through the mounting points.
- Per-cable sensing spreads heat across the module's two or three cable shunts rather than concentrating it. Each per-cable shunt and its coin or via field is a hotspot, so the copper-pour, thermal-via, and chassis-coupling treatment applies at each one.

### 6.7 High-current layout, stackup, and vias (guidance; PENDING per-module per OQ-12)

Working 4-layer stackup for a high-current sensing module roughly the width of its connector:

- L1: sensors and components, including the shunts.
- L2: ground pour, also carrying combined return current.
- L3: rails (power).
- L4: smaller signaling and sense.

Each high-current path (a rail on the 24-pin, a cable's bundled 12V on EPS/PCIe) detours from L3 up through a via array to its shunt on L1 and back. EPS and PCIe carry this path once per cable.

Rules:
- Size each path's via array for full current. For 20A, copper-filled vias or a plated slot beat a large hollow-via field. For the ~40 to 55A EPS/PCIe per-cable class, a copper coin or inlay is the right tool and gives a vertical heat path to the chassis. Budget two or three coins or via fields per EPS/PCIe board.
- Via arrays punch anti-pad voids in the L2 ground pour; keep signal traces and their returns clear of the voids.
- L4 signals reference the split L3 power plane, so expect a return-path discontinuity where a trace crosses a rail boundary. Tolerable for CAN at 500k to 1M and I2C at 400k. Route sensitive nets on L1 over the solid L2 ground.
- Run inner copper at 2 oz on both the L3 rails and the L2 return.
- Alternative to evaluate per module: keep the high-current rails and shunts on L1 in 2 oz so current never leaves the top layer, trading a busier top layer for far fewer high-current vias and an intact ground plane.

Vertical-transition options: copper-filled vias (the practical choice at 20A), plated slots (rail-shaped, sized to a shunt terminal), and copper coins / inlays (for the EPS/PCIe 50A class, with direct through-board heat transfer; a specialty process with higher cost and lead time).

### 6.8 Kelvin sensing (LOCKED, v1.2)

Four-wire Kelvin sensing on every shunt: the sense taps the shunt element only, the force terminals carry the current. Keep the Kelvin sense pair short and local on the top layer next to the shunt and its monitor. Do not route it down to a signal layer and back, which folds via inductance and trace length into the measurement the Kelvin connection exists to protect.

### 6.9 Pro module detail (lead: 12VHPWR Pro)

| Item | Decision |
|---|---|
| MCU | ESP32-P4 |
| Per-pin current sensing | INA240A3 analog current-sense amps on per-pin shunts |
| ADC | LTC2358-18, 8-channel simultaneous-sampling 18-bit SAR (sub-millisecond inter-pin timing) |
| Rail voltage | 47k/10k divider into one LTC2358 channel |
| Streaming | ~50 kHz x 6 channels, about 900 kB/s, over RS-485 (pair 2), module to Hub |
| Control | CAN-FD (pair 3) |
| Reference | Local REF3033 on module (ratiometric correction at the LTC2358-18) |
| Connector (to Hub) | RJ-45 8P8C, locking boot |
| Connector (power path) | 12VHPWR (12V-2x6) soldered directly to the board (Section 2.8) |
| Production BOM | ~$98 to $99 (100-qty) |

Cross-tier note: a Pro module in a Standard Hub runs CAN control and event telemetry normally; its streaming pair is connected at the jack but stays dark because the Standard Hub does not populate an RS-485 receiver. This is the intended graceful-degrade behavior.

### 6.10 Acquisition model: continuous sampling, ring buffer, and ALERT (LOCKED, v1.4)

The digital-sensor modules (24-pin, EPS, PCIe) run their INA228 or INA238 in continuous-conversion mode, and the MCU holds a per-sensor ring buffer of roughly 2 seconds of 1 kHz samples (about 2000 records per channel). The buffer is pre-roll: when a burst or event fires, the captured window already contains the lead-up held in the ring, which a read-on-event scheme cannot reconstruct. So both the part and the read loop run continuously; there is no idle-then-wake path for these modules.

Sampling and averaging: set each sensor's conversion time and averaging (AVG) so the part emits a clean averaged sample at the 1 kHz output rate rather than instantaneous snapshots decimated in firmware. This folds the part's faster internal conversions into each 1 kHz record, lowering noise and anti-aliasing the buffer. The ALERT limit comparison runs on that same averaged value, so threshold response is at the millisecond scale, which matches the 1 kHz record. Sub-millisecond transient capture is not reachable over I2C (OQ-9).

ALERT: the ALERT pin is the event trigger and the threshold detector, not an I2C load. Configure the limit registers (shunt over-voltage for current, power limit, bus over and under-voltage, temperature) so the hardware flags a crossing and raises ALERT, which the MCU uses to freeze and dump the ring buffer (pre-roll plus continued post-roll). Conversion-ready on ALERT also lets the MCU read once per finished conversion instead of polling for fresh data. Servicing an alert is a single DIAG_ALRT flag read per event.

I2C budget: 1 kHz continuous across the 24-pin's four channels sits near the full-round ceiling at 1 MHz (fast-mode plus), with headroom; at 400 kHz, trim the stored fields per sample to current and voltage. The energy and charge accumulators are read at the reporting interval, not the sample rate, so they add negligible traffic. Per-module ring-buffer memory (tens of KB) is trivial in the ESP32-S3 SRAM.

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

Note: the 24-pin ATX figure predates the v1.4 move to four INA228 parts; expect a modest increase over the INA238 baseline (the per-part premium times four). EPS, PCIe, and 12VHPWR lines are unchanged.

---

## 9. Open questions (decisions needed; no assumptions made)

**OQ-1: Hub bulk power input (RESOLVED, v1.3).** The 24-pin module feeds the Hub over a dedicated 2-pin JST-XH 5VSB cable; the Hub then distributes 5VSB to downstream modules over their RJ-45 VCC pins. This removes aggregate current from any RJ-45 pin. The aggregate now sits on the JST-XH feed and the shared PSU 5VSB rail, governed by the total-current cap in OQ-2. See Section 2.5.

**OQ-2: Total 5VSB current cap.** Confirm a firmware cap on total CEC 5VSB draw (the SK6812 LED budget is the main lever) and the maximum LED state to budget for, sized so a fully populated system stays within the JST-XH rating and the shared 5VSB rail with margin. See Section 2.5.

**OQ-3: Precision reference path (RESOLVED, v1.1).** Local REF3033 on each Pro module; no distributed reference; pin 7 reserved as a spare. See Section 3.3.

**OQ-4: Cable length SKUs and policy.** What fixed cable lengths will be offered, and are Pro modules allowed on arbitrary user cables (accepting reduced reference accuracy under Path A) or restricted to characterized CEC cables? Interacts with OQ-3.

**OQ-5: RS-485 topology.** Confirm one receiver per Hub port (point-to-point) versus a shared multidrop bus across ports.

**OQ-6: Module-ID encoding (RESOLVED, v1.7).** Resolved by the DETECT code table in Section 2.3. Pin 8 encodes **link capability** (CAN-only 2.2 kΩ, CAN + RS-485 4.7 kΩ, CAN + 100BASE-T1 10 kΩ, two reserved codes, plus open = absent and short = fault) on a fixed 10 kΩ pull-up to the Hub's 3.3 V ADC reference. That is exactly what the Hub needs to bring up the correct receivers and PHYs; module type and tier are reported over CAN once the link is up. The 24-pin, EPS, PCIe, and 12VHPWR Standard modules are CAN-only (2.2 kΩ); 12VHPWR Pro is CAN + RS-485 (4.7 kΩ).

**OQ-7: Document scope.** Should this document fully specify Enterprise and Mission Critical now, or keep them at platform-summary level until their first customer requirements land?

**OQ-8: 12VHPWR Standard rail accuracy.** This module senses through the ESP32-S3 ADC (INA240 output plus a 47k/10k divider), which caps absolute accuracy near +/- 1%. Accept that as the Standard-tier figure, or add a local REF3033 to this one board for ratiometric correction (improvement is INL-limited, roughly +/- 0.3 to 0.5%)? The precision buyer otherwise steps up to the 12VHPWR Pro.

**OQ-9: EPS/PCIe transient capture.** The INA238 averages, smoothing millisecond CPU/GPU transient spikes out of the reading. If transient visibility on bundled EPS and PCIe is wanted, that argues for the INA240-style fast analog path used on 12VHPWR, at the cost of the integrated I2C convenience. Decide whether bundled EPS/PCIe need transient capture or whether averaged total power is sufficient.

**OQ-10: Bundled-shunt vertical transition.** Lock copper coin versus filled-via field versus plated slot for the ~40 to 55A EPS/PCIe per-cable shunt sites, against cost and fab capability (see Section 6.7).

**OQ-11: Per-module shunt part selection.** Final value, TCR, tolerance, package, and power rating per the shunt table in Section 6.4.

**OQ-12: Per-module high-current stackup.** Lock the L3-rails-with-via-detour stackup versus the top-layer-rails alternative for each high-current module (see Section 6.7).

**OQ-13: Energy reporting scope.** The 24-pin INA228 provides hardware energy and charge on all four rails, including complete 5VSB standby energy, at no added cost. Decide whether energy reporting is scoped to that 24-pin standby and platform figure, or extended to total system energy, which needs energy on the load rails via firmware integration of the INA238 power reading on EPS and PCIe (and the LTC2358 path on 12VHPWR), summed at the host. The 24-pin energy is a partial figure and must not be presented as total. See the energy discussion behind Section 6.1.

**OQ-14: PoE / over-voltage protection scope (spec-versus-board divergence).** Two linked decisions. First, Standard and Pro: this document locks per-pin over-voltage protection platform-wide (Section 2.4), but the PCB repo and current boards drop it on Standard and Pro as of 2026-05-30. Ratify the drop, accepting the unclamped cross-connect exposure on the RJ-45 signal and 5VSB-out pins, or restore the protection and accept the cost, board space, and the VCC series-resistor headroom tradeoff. Second, Enterprise and Mission Critical: decide whether to populate a per-pin TVS array plus series limiting resistors sized for accidental PoE injection (up to ~57V) and transients, per those tiers' deployment environments. If populated, size the VCC series resistor with the power budget (Section 2.4, Section 2.5). This subsumes the PCB repo's OQ-8, renumbered here so it does not collide with the 12VHPWR Standard accuracy question already at OQ-8.

**OQ-15: Shielded (FTP) jack divergence (spec-versus-board).** Section 2.1 locks shielded (FTP) jacks on every Hub and module; current boards place the Amphenol 54602, an *unshielded* 8P8C jack, with the SH1/SH2 board-lock tabs plated and tied to GND — a board-lock ground path, not a 360-degree cable-shield termination. Acceptable for prototype bring-up (the module link carries only CAN, 5VSB, DETECT, and the Standard-dark RS-485 pair, all shielding-insensitive at these rates), but it does not meet the FTP lock for production or EMC, where the Pro RS-485 stream near GPU switching noise and CE/FCC emissions matter. Ratify the unshielded jack platform-wide, or restore a true non-magnetic metal-shell shielded jack (a footprint change plus a J1 re-place on all boards; the cec.pretty FTP-jack footprint is being prepared so the swap is ready). Pairs with the OQ-14 protection divergence.

---

## 10. Revision history

- **v1.8 (this revision):** moved the Hub Standard MCU from the (non-existent) ESP32-S3-MINI-1-N16R2 to the **ESP32-S3-WROOM-1-N16R8** (16 MB flash + 8 MB PSRAM). The MINI-1 form factor has no 16 MB SKU; the WROOM gives the aggregation role real flash/PSRAM headroom and OTA room, and the documented "16 MB flash" intent is preserved. The PCB-antenna keepout is honored (future Wi-Fi option). Modules stay on the MINI-1 (ESP32-S3 family throughout). Vendored the WROOM-1 symbol and footprint in-repo (cec-vendor / cec-RF_Module). No change to the universal interface, sensing, or any open question.
- **v1.7:** finalized the DETECT module-ID encoding (Section 2.3): added the locked code table and corrected the Hub-side divider to a fixed 10 kΩ pull-up to the 3.3 V ADC reference (an ESP32 ADC input pulled to the 5VSB VCC pin would exceed its range), with the encoding now by **link capability** rather than module type/tier — resolving OQ-6. Recorded the shielded-jack divergence as OQ-15: current boards carry the unshielded Amphenol 54602 with grounded SH1/SH2 board-locks rather than the Section 2.1 FTP jack; acceptable for prototype bring-up, open for production/EMC. No change to sensing, pin allocation, or any other locked decision.
- **v1.6:** added Section 2.8, the module PSU-side power-path connectors and interposer-cabling rules, separate from the universal RJ-45 interface. Locked two connector decisions surfaced during 24-pin and 12VHPWR layout: (1) the 24-pin ATX module carries two Molex Mini-Fit Jr male headers (input J3, output J4) because no board-mount female 24-pin ATX receptacle exists as a standard part, so the run from the module output to the motherboard requires a dedicated female-to-female 24-pin ATX bridging cable (a female receptacle on each end, since module output and motherboard are both male headers), which CEC supplies as a platform SKU; (2) the 12VHPWR modules (Standard and Pro) solder their 12VHPWR (12V-2x6) connector(s) directly to the board, with no detachable pass-through header or bridging cable. Cross-referenced the soldered-connector decision in the 12VHPWR Pro detail table (Section 6.9). No change to sensing, the universal interface, or any open question.
- **v1.5:** reconciled against the CEC PCB-repo ground-truth spec (GitHub, 2026-05-30). Adopted the Standard-module MCU lock: the 24-pin, EPS, PCIe, and 12VHPWR Standard modules run the ESP32-S3-MINI-1, the same family as the Hub Standard (Section 1). Added Section 2.7 (Hub bulk power input) with the dedicated 2-pin feed's keying and front-end landing, folding in the repo's fuller detail. Recorded the PoE divergence: the repo and current boards drop per-pin over-voltage protection on Standard and Pro, reversing the Section 2.4 requirement; this document holds the requirement and opens OQ-14 to ratify or reverse rather than inheriting the board state. Logged the reconciliation actions the PCB side owes this document: adopt the INA228 on the 24-pin (pin-compatible with the repo's INA238, no respin), correct 12VHPWR Standard from a single-rail INA238 to six per-pin INA240 into the ESP32-S3 ADC (a board change if built single-rail), state EPS and PCIe sensing as per-cable rather than a single 12V rail, and import the current-handling domain (Sections 6.2 to 6.8), the acquisition model (Section 6.10), the reference resolution with pin-7 reservation, and OQ-8 through OQ-13.
- **v1.4:** the 24-pin moves to the INA228 on all four rails (12V, 5V, 3.3V, 5VSB) for fine bus-voltage resolution, both to capture 12V droop and to detect any uncharacterized droop on the 5V, 3.3V, and 5VSB rails; EPS and PCIe stay on the INA238. Added the acquisition model (Section 6.10): continuous-conversion sensors, a per-sensor ~2 s ring buffer of 1 kHz samples with pre-roll, averaging tuned to the 1 kHz output rate, and ALERT as both the threshold detector and the buffer freeze trigger. Opened OQ-13 (energy reporting scope), noting the 24-pin now carries hardware energy and charge accumulators on every rail. The 24-pin BOM figure is flagged as predating the part change.
- **v1.3:** OQ-1 resolved. Hub bulk power is a dedicated 2-pin JST-XH 5VSB feed from the 24-pin module, with 5VSB distributed to downstream modules over their RJ-45 VCC pins; Section 2.5 rewritten so the aggregate current sits on the JST-XH feed and the shared 5VSB rail rather than any RJ-45 pin; OQ-2 broadened from an LED cap to a total 5VSB current cap.
- **v1.2:** added the module current-handling domain (Section 6): sensing-granularity policy (per-rail on 24-pin, per-cable on EPS/PCIe, per-pin on 12VHPWR), an over-spec current-target table, a production shunt-selection table (superseding the v4 24-pin shunt values), ADC-range and resolution characterization, a no-heatsink thermal stance (copper plus chassis coupling), high-current layout and stackup guidance, and the Kelvin locality rule. Opened OQ-9 through OQ-12 (EPS/PCIe transient capture, bundled-shunt via transition, shunt part selection, per-module stackup). Platform sections (interface, CAN/RS-485, Hub tiers) unaffected; EPS/PCIe sensor counts unchanged and now stated explicitly as per-cable.
- **v1.1:** precision reference resolved to a local REF3033 on each Pro module, no distributed reference, pin 7 reserved as a spare (OQ-3 closed); v4 current-sensing absorbed (INA238 on 24-pin/EPS/PCIe, INA228 as the 20-bit option, INA240 retained on both 12VHPWR tiers, LTC2358-18 on Pro) with a production sensing summary added (Section 6.1); v4 sensing sheet superseded on reference distribution, DETECT, and pin-7 allocation; 12VHPWR Standard accuracy opened as OQ-8.
- **v1.0:** established as platform ground truth. RJ-45 8P8C locked across Standard and Pro with locking boot; Mini-Fit Jr retired; DETECT defined as analog single-wire ID and presence sense; Hub Pro fixed at 8 ports; control confirmed entirely on CAN with RS-485 for streaming only; connector current understanding corrected; precision-reference and bulk-power decisions opened.
- **Prior threads reconciled:** v1.1 Hub Standard (Mini-Fit Jr), v3 architecture (RJ-45), v4 sensing (INA238).
