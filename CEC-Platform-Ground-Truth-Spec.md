# CEC Platform: Ground-Truth Specification

**Status:** Controlled baseline. This document is the single source of truth for the CEC platform and holds precedence over every earlier document. All future decisions are versioned here. Where any earlier document conflicts, this document wins.

**Document version:** 3.7

**Reconciles and supersedes:**
- *CEC Hub Standard v1.1 locked decisions* (Mini-Fit Jr connector): superseded on connector and cabling; all other v1.1 decisions carried forward.
- *Module sensing architecture v3* (RJ-45 connector strategy): adopted as the connector and communication basis.
- *Module sensing architecture v4* (INA238/INA228 sensor selection): current-sensing adopted; superseded on precision-reference distribution, DETECT definition, pin-7 allocation, and 24-pin shunt values, which this document overrides.
- *Early CAN-FD / BOM thread* (JST-XH connector, i.MX 93 Enterprise): superseded.
- *CEC PCB-repo ground-truth spec* (GitHub, 2026-05-30): reconciled here. Its Standard-module MCU lock is adopted; its 24-pin sensor, 12VHPWR Standard sensing, and platform-wide PoE drop diverge from this document and are addressed in Section 2.4, Section 6.1, and OQ-14.
- *Canonical upload v3.4* (subsystem power management / NanoKVM / Concierge branch, 2026-06-04): consolidated into this board-reconciled line at v3.6. Its new architecture is adopted (Section 2.9 subsystem power, Appendix C Concierge, the NanoKVM aux link, and OQ-38..56); its stale board facts (TJA1462A, ESP32-S3-MINI-1-N16R2, the discrete 1 Ω inrush + SS14 front end, aluminum-polymer hold-up, M2.5 mounts) are overridden by this line's as-built decisions and were NOT imported.

**Last updated:** 2026-06-05
**Scope of this revision:** v3.7 (2026-06-05) resolves the NanoKVM aux-link **form** (OQ-51). The link is a reserved keyed **5-pin JST-PH** aux header carrying the full set of pins the NanoKVM exposes on its own header — the full-duplex 3.3 V UART (TX/RX), the **shared 5 V feed and ground** of Section 2.9, and the NanoKVM's **3.3 V reference/presence** line — with **NO trigger GPIO**, since the NanoKVM exposes no drivable interrupt input, so event triggers ride the UART in-band. The baud and framed protocol stay firmware-open. (This corrects a momentary mis-read that the NanoKVM exposed only UART/GND/3V3: it does expose 5 V + GND, so the Section 2.9 shared rail and the wall-wart-through-NanoKVM forensic path stand.) Prior scope: v3.6 consolidated the canonical v3.4 upload (the architecture branch that forked from the shared v3.1 baseline) into this board-reconciled line. It adds **Section 2.9 (subsystem power management, PROPOSED)** — the monitoring subsystem draws from three 5V sources (PSU main 5V tapped after the 24-pin sensor, 5VSB, and a wall-wart through the NanoKVM USB-C) through a hardware priority ideal-diode OR that **extends the as-built TPS2121 PSU/USB front-end mux** (Section 2.7) from two inputs to three, with firmware reading a rail-sense and setting the load budget and mode rather than switching its own supply, a forensic-recovery path (a wall-wart powers the Hub and NanoKVM so flash-persisted data egresses over the NanoKVM's network without opening the case), and persist-on-fault flushing to the Hub's flash on power loss. It also imports **Appendix C (Concierge data collection)** and the **NanoKVM aux-link** row (3.3 V UART + the shared 5 V feed) on the Hub tables. Because both forks independently created an OQ-37, the upload's **OQ-37..55 are renumbered to OQ-38..56**; this line's OQ-37 (shielded jack, resolved to the Kinghelm KH-RJ45-58) is kept. The upload's stale board facts are overridden, not imported. Prior this-line scope (carried forward): v3.5 locked the CAN transceiver to the classical **TJA1051T/3** (CAN-FD deferred, so the FD/SIC TJA1462A no longer earns its place; one trade is the loss of SIC ringing suppression on the optional 1 Mbps, now gated solely on the §3.1 bench SI test). v3.4 adds an optional bus-wide 1 Mbps CAN rate to Section 3.1 — 500 kbps stays the default and the locked floor, 1 Mbps is firmware-only via Hub-led auto-baud with error-counter fallback, gated on the Section 3.1 star/stub SI bench test run at 1 Mbps, and a DETECT-code bitrate advertisement was considered and declined. v3.3 locks the 24-pin dual-feed rule — its RJ-45 VCC pin is no-connect so all bulk 5VSB flows over the dedicated JST feed (Section 2.7), preventing the RJ-45 VCC from paralleling (and, via a short patch, overloading) against that feed. v3.2 reconciles this document against the CEC PCB-repo fork — folding in the repo's locked board decisions this line had not carried (Section 2.8 module PSU-side interposer cabling; the Hub Standard MCU correction to the **ESP32-S3-WROOM-1-N16R8**, since the MINI-1 has no 16 MB SKU; the 4700 µF hold-up corrected from polymer to **aluminum electrolytic**; **M2.5→M3** corner mounts; and the Hub front-end **mux / isolation / blackout-dump** architecture in Section 2.7), and recording the shielded-jack board divergence as OQ-37. Prior v3.1 scope: records the FPGA development-tooling assessment as Appendix B.4 (Claude Code lowers the RTL and verification cost through its simulate-iterate loop, strong on common RTL and testbenches, weak on timing, CDC, and microarchitecture, most automatable on the open toolchain) and the current compute leaning as Appendix B.5 (MCU plus FPGA on the Max conditional on OQ-20, and a Linux-free MCU-or-RTOS control plane plus FPGA-or-switch data plane on Enterprise with the PolarFire SoC as the consolidated candidate). Reflects the leaning in Section 1, OQ-7, and OQ-15. Carries the v3.0 compute exploration (Appendix B), the v2.9 processing-placement principle (Section 1), and the rest of the prior baseline. Enterprise and Mission Critical remain at platform-summary level (OQ-7).

> Action items (v3.2): the Mini-Fit Jr → RJ-45 re-cut is **COMPLETE** on every board (the prior stale-artifact item is resolved). Open board-vs-spec items: (1) the locked low-capacitance **DETECT-pin ESD diode** (Section 2.4, v2.0) is **not yet populated** on the current Standard/Pro boards — add on the next revision; the already-ordered 24-pin rev2 shipped without it. (2) The **FTP shielded jack** (Section 2.1) is not yet placed; boards carry the unshielded Amphenol 54602 — production re-place tracked as OQ-37.

---

## 1. Platform overview

The CEC platform is a modular PC power-telemetry system. Per-rail sensing modules connect to a central Hub over a single commodity cable. The Hub aggregates telemetry and forwards it to the host PC over USB. Four tiers are built from one fundamental design with progressively populated features:

| Tier | Role | Hub MCU | Host link | Distinguishing hardware |
|---|---|---|---|---|
| Standard | Mainstream builders | ESP32-S3 | USB Full Speed | CAN only, 4 ports |
| Pro | Overclockers, bench users | ESP32-P4 | USB High Speed | plus RS-485 streaming, 8 ports |
| Enterprise | Regulated / financial | ESP32-P4 | USB HS (plus optional 1000BASE-T1) | plus RJ-11 trust channel, secure element |
| Mission Critical | Defense, broadcast, render | ESP32-P4 plus crypto | Redundant uplinks | Redundant power, CAN, trust |

Modules are tier-agnostic: any module works in any Hub and degrades gracefully (see Section 8).

Standard-tier modules (24-pin ATX, EPS 8-pin, PCIe 8-pin, 12VHPWR Standard) run the **ESP32-S3-MINI-1**, the same MCU family as the Hub Standard (LOCKED, v1.5; adopted from the PCB repo). The 12VHPWR Pro module runs the ESP32-P4 (Section 6.9), as does the proposed 12VHPWR Max (Section 6.11, P4 with PSRAM).

**Processing-placement principle (design rule).** Process at the lowest layer that cannot move the work up, and push everything else up. A device keeps only the processing that bandwidth or autonomy forbids relocating: the data reduction needed to fit its own uplink, and any decision it must make faster than a round trip to the next layer or while that layer is absent. Everything else, meaning classification whose result only ships upward, trend, history, cross-module inference, and presentation, belongs at a higher layer, where compute is amortized across modules, context spans the whole system, and an update lands in one place rather than across a fleet. The corollary is to spend bandwidth before silicon: absent a hard autonomy requirement, give a node a faster uplink and let the layer above do the work, since each layer up (module, Hub, host, self-host service) is cheaper to build and easier to update in every way except latency and locality. This is the baseline that OQ-15 and OQ-20 (Max capture versus report) and OQ-7 (Enterprise build) resolve against. Overshoot signals, where work should move up a layer: a module storing history, a module running a learned model whose only output ships upstream, a module computing something that needs another module's data to mean anything, or any device sized for its peak-analysis case instead of its local-decision case. The compute-architecture leanings that follow from this principle, MCU plus FPGA on the Max and a Linux-free MCU-or-RTOS control plane on Enterprise, are recorded in Appendix B.5 and refine the simple Hub-MCU column above.

---

## 2. Universal physical interface

### 2.1 Connector (LOCKED)

- Module-to-Hub connector is **RJ-45 (8P8C)** for all tiers, all modules and Hubs. Mini-Fit Jr is retired platform-wide.
- **Locking-boot RJ-45 is the default** shipped in the box, chosen to remove the silent-dropout failure mode of a plain clip in a transported or vibrating chassis. Mechanical-keyed variants remain available for high-security deployments.
- Shielded jacks (FTP) on Hub and modules. (Board divergence: current prototype boards carry the unshielded Amphenol 54602 with grounded board-locks — OK for prototype bring-up; FTP is the production target, tracked as OQ-37.)

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
| 8 | Pair 4 | Brown | DETECT (presence + comm-class, analog single-wire sense) | All |

Notes:
- CAN runs classical at 500 kbps on every tier, on the same pair (Section 3.1).
- Pair 3 (pins 3 and 6) is the T568B split pair but stays twisted in the cable; standard practice for differential CAN.
- Standard tier leaves pair 2 unused, terminated at the module side.

### 2.3 DETECT: presence and comm-class sense (LOCKED; OQ-6 resolved v1.7)

Pin 8 is an analog single-wire presence and comm-class sense. Each module carries one resistor from pin 8 to GND. The Hub reads pin 8 through a fixed 10k pull-up to its local 3.3V rail (not the 5VSB VCC, so the divider output stays inside the ADC input range), forming a divider it converts on an ADC channel.

The resistor encodes only what the Hub must know before the module talks: that a module is present, and which link to bring up on the port. Module category, exact type, tier, unique serial (the module MCU's factory MAC), and any per-unit data are reported over CAN on enumeration, which is an unlimited namespace. Identity is a data problem, so the pin carries only the physical-layer decision. This keeps the code table small and fixed: it does not grow as module categories or models are added.

Enumeration is host-independent: identity rides CAN and the module network runs on 5VSB, so the Hub enumerates every module at power-up even with the PC off. The only thing a port-level sense or a host bus adds over that is the physical port-to-module mapping, which is needed solely to bring up a per-port streaming link, and that matters only when the host is present to consume the stream. So presence and identity never depend on the host, the sense line, or USB.

| Code | ID resistor (E24, pin 8 to GND) | V at pin 8 (3.3V, 10k pull-up) | Meaning |
|---|---|---|---|
| Link: CAN-only | 2.2 kΩ | 0.595 V | Standard modules and any low-rate module; no streaming receiver |
| Link: CAN + RS-485 | 4.7 kΩ | 1.055 V | Hub enables the RS-485 receiver on the port (Pro) |
| Link: CAN + 100BASE-T1 | 10 kΩ | 1.650 V | Hub brings up the 100BASE-T1 PHY (Max, contingent on OQ-20) |
| Reserved link A | 22 kΩ | 2.269 V | Future link type |
| Reserved link B | 47 kΩ | 2.721 V | Future link type |
| No module | open | ~3.3 V (rails to pull-up) | Port empty or cable broken |
| Fault | short to GND | 0 V | Solder bridge or damaged cable |

Codes sit ~0.45 to 0.62V apart, far above the worst-case error (ESP32 ADC nonlinearity, the 3.3V rail tolerance the ADC does not reference, and 1% resistors), so nothing collides. The resistor is a pure code, so it needs no precision or TCR spec; a standard 1% 0402/0603 is fine, the opposite of the shunts. Because it is kΩ-scale, cable and contact resistance (under 1Ω, drifting with insertion cycles) is below 0.1% of the divider, so this sense is immune to the contact-resistance drift that helped kill the distributed reference.

Why 3.3V rather than 5V: the 5VSB on pin 1 could pull the divider up over a wider 0 to 5V span, spreading the codes further apart, but that gain does not survive the ADC. The ESP32 and S3 ADC top out near 3.3V with an absolute max around 3.6V on a pin that is not 5V tolerant, and an empty port pulls the line to the full reference, so a 5V pull-up puts about 5V on the ADC for every open port, over-ranging the read and stressing the pin. Scaling each port back under 3.3V at the Hub ADC would add a divider per port and land right back in the 3.3V window, so the span gain cancels. 5VSB is also a loose, noisy standby rail, looser than the Hub's local regulated 3.3V, and since the ADC references its own bandgap rather than the rail that error is uncompensated, which is the error the pin-7 Kelvin return exists to remove. A 5V line would also break the pin-8 module sense tap behind poke-and-ack, since the module ESP32 cannot take 5V either. The wider namespace a 5V span would buy is not needed, since identity lives on CAN and this table is small and fixed.

Limitation: the resistor maps a port to a link class, not to a unique module, so when two same-class modules coexist the Hub knows both ports hold (for example) an RS-485-class module but not which serial is on which port until it correlates over CAN. For the usual one-of-each build this never arises. If per-port unique identity ever becomes a requirement (repeated modules, Enterprise/MC fleets), the upgrade path is a 1-Wire ID and EEPROM on pin 8 with pin 7 as its return, carrying a unique serial and on-module storage read per-port and before boot. Not adopted here.

Port-to-identity binding (poke-and-ack, v2.6): the Hub binds each CAN-enumerated identity to its physical port without putting identity on the pin. Because the Hub holds a separate pull-up on each DETECT line, it briefly perturbs one port's line; the module on that port senses the change on a high-impedance pin-8 input tap and reports over CAN that its line moved; the Hub, knowing which port it poked, binds that serial to that port. It walks the ports in sequence, or drives a distinct low-rate pattern per port to bind them all in one pass. The code table is untouched and identity stays on CAN, so this spends no namespace: the pin carries one bit of per-port selection and CAN carries the identity. It runs host-independent at standby and re-runs on hot-plug for any newly announced module. It needs a module-side tap from pin 8 to a GPIO or ADC input (today's modules carry only the passive resistor), and it coexists with a pin-7 Kelvin return on the same pair.

Compatibility: the current prototype modules have no pin-8 sense tap, so they will not respond to a poke even on a Hub built with the feature. The Hub treats a silent port as a legacy module, still known from CAN and read for comm-class from the static divider, just not poke-bindable. So poke-and-ack is an opt-in enhancement that degrades to today's known-but-unbound behavior for any module without the tap, and a new Hub can freely mix poke-capable and legacy modules.

Pro and up can bind without the poke: a Pro module's per-port RS-485 streaming pair is already point-to-point, so bringing the receiver up on a port and seeing whose stream appears binds that port to its identity. A no-module-change option for hot-plug is per-port 5VSB current, where the port whose draw rises as a new identity announces on CAN is that module's port, though this cannot disambiguate a cold boot where every port powers up at once. Open details are in OQ-28.

Pin 7 candidate uses (exploration, v2.2; none adopted): the spare pin's realistic uses are narrow, because the architecture already covers the obvious ones elsewhere. The one concrete improvement is a dedicated Kelvin return for the DETECT divider: routing pin 7 as the divider's current-free low-side reference removes the IR-drop error from the module's 5VSB draw on the shared ground (on the order of 100 to 150 mV at a few meters and a few hundred milliamps), which scales with cable length (OQ-4). That conflicts with keeping pin 7 as a driven signal, so allowing both the Kelvin return on sensor ports and the deferred Max trigger (Section 6.11) on a Max port would require a per-port pin 7 at the Hub rather than one shared bus. Uses considered and set aside as redundant: 1-Wire identity and EEPROM (per-port identity is already the module MCU MAC over CAN, and per-unit calibration lives in module flash); a hardware power-state line from the 24-pin module (modules run on 5VSB and are on CAN before the main rails come up, so the co-capture FREEZE already covers the power-on transient, Section 6.10); out-of-band firmware recovery (modules have local USB, and a single line cannot sequence the ESP32 boot-mode entry); a second comm channel or a redundant power pin (CAN covers the first, and moving bulk power to the JST-XH feed removed any RJ-45 current pressure for the second). Pin 7 stays reserved pending a decision.

### 2.4 Cross-connect and PoE protection (RESOLVED for consumer, v1.9; Enterprise/MC deferred to OQ-7)

Decision (v1.9): consumer tiers (Standard and Pro) do not carry per-pin PoE-grade over-voltage protection on the RJ-45 module interface. This ratifies the board state and closes the consumer half of OQ-14.

Rationale: the RJ-45 here is an internal module-to-Hub interconnect inside the PC, not a port that faces building network wiring. Reaching it with 57V PoE means deliberately running a live PoE cable into an open case and into a telemetry jack, which is misuse rather than an accident. The realistic accident, plugging a module or Hub into an ordinary non-PoE network jack, puts only low-voltage Ethernet signaling on the pins, and the dominant interconnect (CAN, pins 3 and 6) runs through the TJA1051T/3, whose bus pins carry the automotive transceiver class's own bus-fault and ESD protection (confirm the exact fault and ESD ratings against the TJA1051T/3 datasheet). Dropping the protection also returns the VCC series-resistor drop to the 5VSB budget, removing the headroom tradeoff that the layout caution below was about.

One carve-out is decided on its own, separate from the PoE clamp: the DETECT pin (pin 8) feeds the ESP32 ADC directly and has no inherent protection, and the platform hot-plugs modules, so insertion ESD lands on a bare analog input. A single low-capacitance ESD diode on pin 8 is locked into every Hub and module (decision, v2.0). It is cheap, does not touch the 5VSB headroom question, and stands even though the PoE-grade network is dropped. The CAN pins lean on the transceiver; the analog DETECT pin is the one exposed node with nothing behind it.

Enterprise and Mission Critical (deferred to OQ-7): the module-to-Hub RJ-45s on those tiers are equally internal and inherit the consumer answer. What can face building infrastructure where PoE sources live is an external uplink, currently specced as the optional 1000BASE-T1 host link, which is a different connector with its own magnetics and protection story. So the over-voltage question for those tiers attaches to the uplink port, not the module interface, and is decided when Enterprise and Mission Critical are specified in full (OQ-7).

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
- Lands on the Hub's existing 5VSB front end: TPS2121 priority power mux (source-side reverse-current blocking + soft-start inrush limiting), the D1 reverse-isolation Schottky, the 4700 uF hold-up, and the TPS3839K33 supervisor — see the front-end architecture below. As an internal PC power lead it is not exposed to the commodity-cable cross-connect threat of Section 2.4, so it carries no per-pin over-voltage network; reverse-polarity and inrush protection still apply (now via the mux, not a discrete resistor/diode). Section 2.9 (subsystem power management) gives that mux + D1 a second job: blocking the shared monitoring rail and the forensic wall-wart from back-feeding up the 5VSB line into a dead PSU — so the mux's source-side reverse blocking must be confirmed against that path (OQ-55).

Hub Standard front-end architecture (PCB-repo design, folded in v3.2): the 5VSB-in and the USB-C VBUS are OR-ed through a **TPS2121 priority power mux** (PSU 5VSB preferred; USB VBUS is the backup so the Hub enumerates on a bench with no PSU connected). A **reverse-isolation Schottky (D1)** downstream of the mux feeds an **isolated +5V_HOLD reservoir node** — the 4700 µF aluminum-electrolytic hold-up cap and the LP5907 LDO input sit behind it — so the reservoir cannot back-feed or smooth the 5VSB rail the platform is measuring. (D1 is **built as SB120**, 1 A/20 V; **SS14**, 1 A/40 V, is a drop-in higher-margin alternative — either is adequate on the 5 V rail.) The mux's own soft-start (C_SS ≈ 2.2 µF) ramps the bulk-cap charge, so the v1.1 discrete 1 Ω 1 W inrush resistor and a separate reverse-polarity diode are **superseded** by the mux and are not populated. A divider on the shared +5VSB into an ESP32 ADC pin (GPIO8) is the **blackout-sense** input: on PSU power loss the MCU rides the +5V_HOLD reservoir (~tens of ms) and dumps its last telemetry window to flash. A small (~470 µF) bulk cap on the +5VSB distribution rail rides out downstream-module load steps. Measurement integrity holds because the PSU 5VSB is sensed upstream at the 24-pin module, ahead of the cable and the mux.

24-pin module dual-feed (LOCKED, v3.3): the 24-pin ATX module is unique in being both the bulk 5VSB **source** (over the dedicated JST feed above) and a normal module on a Hub RJ-45 port. Its **RJ-45 VCC pin (J1 pin 1) is left no-connect — not tied to the module's +5VSB** — so all bulk current flows over the JST as OQ-1 intends. The module is self-powered from its own 5VSB tap and never needs the Hub's distributed VCC; RJ-45 GND/CAN/DETECT stay connected (the parallel GND return is beneficial). This is required, not cosmetic: the JST lands at the Hub power-mux **input** and the RJ-45 VCC at its **output**, so the mux series resistance (~56 mΩ, TPS2121) sits in the JST leg only. Commoned on the module, the two VCC pins parallel each other, and a short RJ-45 patch makes the RJ-45 the **lower-resistance** path — it would then carry the majority of the bulk current on the 1.5 A-rated RJ-45 contact (over its rating near full load) and bypass the mux's PSU/USB OR-ing (back-feeding the +5VSB rail, e.g. leaking USB-only bench power into an unpowered 24-pin). Other modules are unaffected — their RJ-45 VCC is their only 5VSB source and stays connected. The ordered rev2 24-pin carries the parallel path; the board docs hold the prototype-run mitigation and the Hub-side workaround options, and the no-connect fix lands on rev3.

### 2.8 Module power-path connectors (PSU side) — interposer cabling (LOCKED, repo v1.6; folded in v3.2)

Separate from the universal RJ-45 module-to-Hub interface (Sections 2.1 to 2.7), each sensing module is a power-path interposer: PSU rail current enters the module, passes through its shunts, and continues to the load. The PSU-side connectors are module-specific (not universal) and are locked per module as follows.

**24-pin ATX module — two male headers; female-to-female output cable required.** Gender convention for this spec: the board-mounted headers are **male** (pin-side), and a cable end that plugs onto a header is **female** (socket/receptacle) — so the PSU's own 24-pin cable is the female inserting connector. The module carries two Molex Mini-Fit Jr (5569 family) 24-circuit **male headers**: one on the PSU side (input, J3) and one on the motherboard side (output, J4). No board-mount **female** 24-pin ATX receptacle exists as a standard part, so the module cannot present a female socket on either side; both connectors are therefore male, the same gender as the motherboard's own 24-pin header.
- Input: the PSU's existing 24-pin cable (a female receptacle housing) plugs directly onto the module input header. No new cable is needed here.
- Output: the motherboard's 24-pin connector is also a male header, so the module output (male) and the motherboard (male) cannot be joined by an ordinary PSU-style cable, which is female on only one end. The run from the module output to the motherboard requires a dedicated **female-to-female 24-pin ATX bridging cable** — a female receptacle on each end, since each end plugs onto a male header (the module output and the motherboard). No standard off-the-shelf product carries a female on both ends, so CEC must supply this cable as a platform SKU.

**12VHPWR modules (Standard and Pro) — connectors soldered to the board.** The 12VHPWR module does not use detachable pass-through headers and does not need a bridging cable. Its 12VHPWR (12V-2x6) connector(s) are soldered directly to the module PCB (board-mounted). On the platform's highest-current, melt-prone connector this removes a mated-contact pair from the power path and keeps the connection deterministic.

### 2.9 Subsystem power management (PROPOSED; architecture adopted, parts and module-rail scope open)

The monitoring subsystem (the Hub, the NanoKVM, and on the open fork below the module fleet) draws from one of three 5V sources, selected in hardware, with firmware setting the load budget and operating mode to match. This does two things the single-5VSB feed of Section 2.5 cannot: it escapes the S0 limb of the 5VSB budget, and it lets a customer recover the Hub's data from a completely dead system without opening the case.

Sources and priority (high to low):
- **PSU main 5V**, present when the PC is running (S0), tapped downstream of the 24-pin module's 5V sensor so the subsystem's own draw is measured and counted in system 5V rather than hidden in standby overhead (OQ-13). This is the large rail (the 24-pin 5V is sized for 20A), so it carries the high-draw S0 state, LEDs included.
- **PSU 5VSB**, present whenever the PSU has AC, over the 24-pin module's existing JST-XH feed (Section 2.7). The standby rail, roughly 2.5 to 3A shared with the motherboard standby, governed by the OQ-2 cap.
- **Wall-wart 5V**, present only when a customer plugs a 5V USB supply into the NanoKVM's USB-C with the PC fully dead. The last-resort forensic source.

Source selection is hardware, a priority ideal-diode OR (main 5V, then 5VSB, then wall-wart), rather than a firmware switch. This extends the Hub's as-built TPS2121 PSU/USB priority mux (Section 2.7) from two inputs to the three subsystem sources — the same TI PowerPath family the OQ-55 part search names (TPS2116 / LTC4412-class). Firmware runs on the Hub MCU, which is powered by the rail it would be switching, so a firmware-controlled switch can deadlock the MCU if it selects a source that is not solid. The firmware instead reads which source is live on a rail-sense and sets the load budget and mode: full budget and normal monitoring on main 5V, the standby cap (OQ-2) on 5VSB, and a minimal LEDs-off forensic-extraction mode on the wall-wart. It may gate the main-5V enable once the PC is confirmed stably up, but the 5VSB fallback stays hardware-automatic. This is priority switching, with the OR isolating the idle inputs, and the rails are never paralleled to sum their capacity, which they do not need since main 5V alone is ample.

Back-feed isolation is the safety-critical rule. Every source feeds the shared rail through its own ideal diode or series element, and the shared rail must never push power back toward a source or into a dead system. In particular the wall-wart, when it is the source, must not travel up the Hub's 5VSB input into a dead PSU's standby rail and the motherboard, nor up the NanoKVM's slot path into the dead PSU. The Hub's existing TPS2121 priority power mux (Section 2.7) already provides source-side reverse-current blocking on its 5VSB input, and the downstream D1 reverse-isolation Schottky walls off the +5V_HOLD reservoir; confirm the mux's reverse blocking covers the shared-rail path back into the 5VSB source, and add the matching isolation on the NanoKVM's slot input.

The shared rail spans the Hub-to-NanoKVM cable, so both boards sit on it and the cable's 5V conductor carries the subsystem current in whichever direction the live source dictates: Hub to NanoKVM on the PSU rails, NanoKVM to Hub on the wall-wart. Size that conductor and its ground for the full subsystem draw. The power feed shares the reserved aux header and cable with the UART link of Appendix C.7: a single **5-pin JST-PH** header carries the shared 5 V, ground, the full-duplex 3.3 V UART (TX/RX), and the NanoKVM's 3.3 V reference/presence line — the full set of pins the NanoKVM brings out on its own header (UART1 TX/RX, GND, 3V3, 5V/GND; its two header grounds common at the connector). There is no separate trigger conductor: the NanoKVM exposes no drivable interrupt input, so event triggers ride the UART in-band (resolved, OQ-51 v3.7). Whether the module fleet also rides this shared rail (the whole-platform dual-feed that frees on-board LED brightness on a maxed build by moving the operating draw to main 5V in S0) or stays on 5VSB-only with the discretionary loads offloaded individually (per-load) is OQ-53.

Forensic recovery (the dead-system case, ties OQ-48). With no PSU power, the customer plugs a wall-wart into the NanoKVM's externally accessible USB-C. That powers the NanoKVM, which powers the Hub over the shared rail, so the monitoring island runs decoupled from the dead PC. The Hub serves its persisted data to the NanoKVM over the UART, and the NanoKVM egresses it over its own Ethernet or WiFi, so the data comes out without opening the case or reviving the PSU. The draw in this mode is the Hub plus the NanoKVM with the LEDs off, around an amp, which any phone charger covers. The external power-in is the NanoKVM's USB-C if it is bracket-accessible on the PCIe card; a CEC power-in port on a rear bracket is the more general option and also revives a Hub-only build (OQ-54).

Persist-on-fault. Forensic recovery returns only what the Hub already wrote to its 16 MB flash, since the volatile ring buffers are gone the instant power dropped. The Hub therefore flushes critical events and frozen windows to flash as they occur, with a final flush on total power loss that the 4700 uF hold-up rides, which gives the hold-up cap a second job beyond the source changeover and sets part of its sizing (OQ-56).

*(Flowchart to be drawn as cec-subsystem-power-management.svg; the hardware priority-OR and the firmware sense-and-set-budget split are captured in the pseudocode below.)*

```text
# ===========================================================
# CEC monitoring-subsystem power management
# ===========================================================
#
# HARDWARE (automatic, no firmware in the loop):
#   3 x 5V sources feed ONE shared monitoring rail through a
#   priority ideal-diode OR. Priority: main 5V, then 5VSB,
#   then wall-wart. Every source is isolated, so the shared
#   rail can never push power back toward a source or into a
#   dead system.
#     main 5V  : tapped downstream of the 24-pin module's 5V
#                sensor, so the subsystem's own draw is measured
#                and counted in system 5V (OQ-13)
#     5VSB     : the 24-pin module's existing JST-XH feed;
#                Hub TPS2121 mux (Sec 2.7) blocks back-feed
#     wall-wart: 5V into the NanoKVM USB-C (external bracket),
#                isolated from the NanoKVM slot-power path
#   Hub and NanoKVM both sit on the shared rail, which spans the
#   inter-board cable; the 5V conductor carries the subsystem
#   current in whichever direction the live source dictates.
#
# FIRMWARE (Hub): never switches the source (that would deadlock
#   the MCU doing the switching). It senses the live source and
#   sets the load budget and operating mode to match.

state ACTIVE_SOURCE   # MAIN5V | SB5VSB | WALLWART | NONE
state MODE

loop every control_tick:
    src = read_rail_sense()                  # ADC/GPIO on the rail
    if src != ACTIVE_SOURCE:
        ACTIVE_SOURCE = src
        switch src:
            MAIN5V:                          # PC running, large measured rail
                set_budget(led = FULL,        load = FULL)
                MODE = NORMAL_MONITORING
            SB5VSB:                          # PC standby, ~2.5A shared rail
                set_budget(led = STANDBY_CAP, load = STANDBY_CAP)   # OQ-2
                MODE = STANDBY_MONITORING
            WALLWART:                        # PC dead, external forensic power
                set_budget(led = OFF,         load = MINIMAL)
                MODE = FORENSIC_EXTRACTION

    if MODE == FORENSIC_EXTRACTION:
        serve_persisted_records_over_uart()  # NanoKVM pulls, egresses over net

# -----------------------------------------------------------
# Persist-on-fault: forensic recovery returns only what is in
# flash, so critical data is persisted as it happens, with a
# final flush on total power loss that the hold-up cap covers.
# -----------------------------------------------------------
on critical_event(e):                        # threshold cross, freeze, fault class
    flush_to_flash(e)                         # durable immediately

on power_loss_detected():                    # main 5V AND 5VSB both sagging
    flush_to_flash(pending_records)           # final flush; 4700 uF rides the window
```

Open items: the source-OR part and back-feed isolation verification are OQ-55, the module-rail scope is OQ-53, the external power-in is OQ-54, and the persist-on-fault behavior and hold-up sizing are OQ-56.

---

## 3. Communication architecture

### 3.1 CAN: control and low-rate telemetry (LOCKED; classical everywhere, v2.0; optional bus-wide 1 Mbps, v3.4)

- All control and command traffic lives entirely on CAN, on pair 3, for every tier. Commands run Hub to module here, since RS-485 is upstream-only (Section 3.2).
- Why CAN and not USB or another host bus: CAN is multi-master, peer, broadcast, and multi-drop, and it runs on 5VSB independent of the PC. Those properties are load-bearing. The cross-module co-capture freeze (Section 6.10) needs one module's frame to reach every module at the same instant with no host in the loop, which a single-host polled bus like USB cannot do; always-on monitoring through standby, boot, and shutdown needs the module network alive when no USB host exists; and priority arbitration gives deterministic alert latency. A host bus on the spare pair (the USB exploration in Section 2.3) would be a host-direct channel for firmware, debug, bulk, and richer enumeration, complementing CAN rather than replacing it. Host-independent enumeration stays on CAN regardless: a module announces its category, type, tier, and serial on CAN at power-up (Section 2.3), with no host required.
- Classical CAN at 500 kbps on every tier, Standard through Mission Critical. CAN-FD is not used by default (decision, v2.0).
- Rationale: neither MCU runs CAN-FD in silicon. The ESP32-S3 TWAI is classical only, and the ESP32-P4 TWAI is also classical and treats FD frames as errors, so FD would require an external MCP2518FD over SPI on every Pro module and Hub rather than a configuration change. With RS-485 carrying the high-rate streaming (Section 3.2), the CAN control plane stays light, and 500k classical covers commands, enumeration, alerts, and periodic status with headroom. Classical also keeps the one shared bus uniformly compatible: a classical-only Standard module dropped onto a Pro Hub running FD would read every FD frame as a form error and answer with error frames, corrupting the bus, so any mixed build forces classical regardless. Running classical everywhere preserves the any-module-any-Hub rule without a per-node FD controller.
- Transceiver: TJA1051T/3 — classical high-speed CAN, VIO = 3.3 V variant (LCSC C38695). LOCKED to the classical part v3.5 (2026-06-05): with CAN-FD deferred platform-wide the FD/SIC-capable TJA1462A no longer earns its place — TJA1051T/3 is cheaper (~$0.40 vs ~$1.02), far better stocked (~121k vs ~166), pin-compatible SO8, and fully covers the locked 500 kbps floor. The one trade is that TJA1051T/3 is NOT a SIC (ringing-suppression) part — see the optional 1 Mbps note below for the signal-integrity consequence. (The earlier TJA1462A existed only to keep the now-deferred FD door open.)
- CAN-FD is deferred, not foreclosed. It earns its place only against a concrete requirement: large single-frame control transfers (for example calibration tables or firmware) where bench USB and RS-485 will not serve, or Enterprise fleet node counts that genuinely saturate 500k. In those cases it brings the external MCP2518FD per node and the constraint that the whole bus segment must be FD-capable, and it is scoped to the Enterprise spec (OQ-7).
- Termination: fixed 120 ohm split at the Hub.
- Optional bus-wide 1 Mbps (added v3.4; 500 kbps stays the default and the locked floor, and CAN-FD stays deferred). The whole bus MAY run classical CAN at 1 Mbps — never per-module, and never a per-tier mix. CAN is one shared medium: a single TJA1051T/3 sits on one CAN_H/CAN_L net across all ports with one split termination, so every node runs one bitrate, and a node clocked at the wrong rate samples every bit in the wrong place and floods error frames, corrupting the bus exactly as a classical/FD mix would. The gain is bandwidth where CAN is the only pipe: 1 Mbps roughly halves the Section 6.10 frozen-window readout time and doubles the Section 7 ARGB-over-Hub headroom, so Standard — the only CAN-only tier, with no RS-485 fallback — benefits most, though the speed-up is shared across the bus, not Standard-private. It is firmware-only: both MCUs' TWAI and the TJA1051T/3 already support 1 Mbps, and the Hub CAN front-end needs no hardware change (the 120 ohm split termination is unchanged and nothing filters the lines). CAVEAT from the v3.5 transceiver lock: the TJA1051T/3 is a plain, non-SIC transceiver, so the active ringing suppression a SIC part (the former TJA1462A, run classical) would have given in the star/stub topology is gone. The optional 1 Mbps therefore rests ENTIRELY on the Section 3.1 bench SI test passing on the passive topology with no transceiver-side help; the locked 500 kbps floor is unaffected. If 1 Mbps is ever needed and proves marginal, revisit a SIC transceiver run classical for that option specifically.
- 1 Mbps negotiation is firmware, with no hardware and no namespace: Hub-led auto-baud with error-counter fallback. The Hub brings the bus up at the configured rate, modules come up listen-only and lock to it, and if the TWAI error counters climb on a marginal install the Hub drops the whole bus back to 500 kbps. A DETECT-code advertisement of per-module bitrate capability was considered and DECLINED: it would cost a module-side resistor change and grow the locked Section 2.3 DETECT table, and it buys nothing, since every CEC module is already 1 Mbps-capable and the real variable is per-install cable and stub signal integrity, which DETECT cannot sense.
- Bench item: the star topology with up to 8 stubs must be signal-integrity verified — the risk is star termination plus stub length. Run it at 500 kbps and at 1 Mbps side by side, eye and ringing measured at the furthest module on the longest cable SKU and worst stub count — now with the plain TJA1051T/3 (no SIC ringing suppression), so this passive-topology result is the sole gate on the optional 1 Mbps rate above.

### 3.2 RS-485: data streaming only (LOCKED; topology pending)

- RS-485 carries high-bandwidth telemetry streaming exclusively, one direction, module to Hub, on pair 2. It carries no control traffic.
- Why RS-485 and not the host bus on the spare pair: the case is softer than CAN's, since USB Full Speed could carry the byte rate. RS-485 is kept because it terminates at the always-on Hub rather than the PC, which preserves the Hub as the timestamping aggregator instead of a passthrough; because each port gets a dedicated free-running pipe with no host scheduling; and because the streaming pair is where the high-rate future lives (100BASE-T1 for the Max), which Full Speed over Cat5e cannot reach. It is the link most worth re-examining if a host bus on the connector were ever made always-on and Hub-terminated.
- Present on Pro modules and Pro+ Hubs. Standard does not populate it.
- Lead case: 12VHPWR Pro streams about 900 kB/s, roughly 7 to 10 Mbps on the wire.
- Working basis: one RS-485 receiver per Hub port (point-to-point per port), which scales cleanly to the 8-port Pro. Confirm against a shared multidrop bus (see OQ-5).
- Bench item: verify rate margin and signal integrity at the maximum offered cable length before locking the streaming protocol. This is the classic case that passes on a 1m bench cable and fails on a 5m customer run.
- Divergence (proposed, OQ-20): the proposed 12VHPWR Max (Section 6.11) replaces RS-485 with 100BASE-T1 single-pair on pair 2 for that one module, which requires the Hub to terminate 100BASE-T1. RS-485 stays the locked streaming basis platform-wide until OQ-20 ratifies the per-module link and the Hub change.

### 3.3 Precision voltage reference (RESOLVED, v1.1)

The platform goal is roughly +/- 0.15% rail-voltage accuracy via a 3.000V REF3033 and ratiometric correction.

**Decision: local reference on each Pro module. No distributed reference. Pin 7 is a reserved spare.**

Each Pro module carries its own REF3033 (about $1 to $2) feeding ratiometric correction at the LTC2358-18. Distribution over the cable was rejected for three reasons: calibrating the DC cable drop ties Pro modules to characterized lengths and fights the RJ-45 any-length appeal; RJ-45 contact resistance drifts with insertion cycles and vibration; and the reference would run single-ended on pair 4 next to the RS-485 streaming pair, so streaming edges couple onto it as an AC error that cannot be calibrated out, only filtered.

The sensor line settles this further. The 24-pin senses with the INA228 and the EPS and PCIe with the INA238 (see Section 6), each of which carries its own internal reference and has no external-reference input, so it can neither use nor needs a distributed reference, and it is already tight (around +/- 0.1% typ). The only Standard module on a raw ADC is the 12VHPWR Standard (INA240 into the ESP32-S3 ADC); if it needs tighter accuracy, a local reference on that one board beats distribution (see OQ-8).

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
| MCU | ESP32-S3-WROOM-1-N16R8 (16 MB flash + 8 MB PSRAM; PCB-antenna keepout honored for future Wi-Fi). The MINI-1 form factor has no 16 MB SKU, so the aggregation Hub uses the WROOM; modules stay on the MINI-1. |
| CAN transceiver | TJA1051T/3 |
| Regulator | LP5907 LDO |
| Hold-up | 4700 uF / 16 V aluminum electrolytic on the isolated +5V_HOLD node (Panasonic EEVFK1C472M); corrected from "aluminum polymer" (unobtainable at 4700 uF). See the Hub front-end architecture in Section 2.7. |
| Inrush limiting | TPS2121 mux soft-start (C_SS ≈ 2.2 uF) — supersedes the v1.1 discrete 1 ohm 1 W series resistor (not populated). See Section 2.7. |
| Reverse polarity / isolation | TPS2121 source-side reverse blocking + D1 reverse-isolation Schottky to +5V_HOLD. D1 built as SB120 (1 A/20 V); SS14 (40 V) is a drop-in higher-margin alternative. |
| Supervisor | TPS3839K33 (3.3V-rail brownout/POR), RESET → ESP32 EN |
| Storage | ESP32-S3 internal flash, 16 MB (~10 MB available) |
| Identity | Factory MAC plus database mapping (no eFuse, no secure element) |
| LEDs | 7x SK6812 MINI-E RGB chain, with firmware current cap per Section 2.5. Data line buffered 3.3 V -> 5 V by an SN74AHCT1G08 (U6, a single 2-input AND with both inputs tied = AHCT buffer) + 330 ohm series (R14) so the ESP32's 3.3 V GPIO clears the 5 V SK6812 V_IH; no LED dimming (added 2026-06-05; the equivalent 74AHCT1G34 buffer was the first pick but is not stocked by JLCPCB, so the 1G08-as-buffer is used in the same SOT-23-5 land). |
| LED control | Adalight via CDC plus CEC override priority |
| Service button | Hidden, GPIO0 (download mode) |
| Mounting | 4x M3 corner holes, chassis-grounded (PC-standard fastener; MountingHole_3.2mm_M3_Pad_Via) |
| PCB | 4-layer 1.6 mm, ENIG, matte black |
| Chassis | Plastic prototype; aluminum 6063 anodized production |
| Bulk power input | Dedicated 2-pin JST-XH 5VSB feed from the 24-pin module (OQ-1 resolved); 5VSB distributed to downstream modules over their RJ-45 VCC pins |
| NanoKVM aux link | Reserved keyed **5-pin JST-PH** header (form LOCKED v3.7, OQ-51) carrying the full-duplex 3.3V UART (TX/RX), the shared 5V power feed, ground, and the NanoKVM's 3.3V reference/presence line — the full pin set the NanoKVM exposes (UART1, GND, 3V3, 5V/GND). The 3V3 line is sensed as **untrusted** — presence plus ratiometric health against the Hub's own +3V3, never used as a reference. **No trigger GPIO** (the NanoKVM has no drivable interrupt input; triggers ride the UART in-band). Local visual-and-electrical fusion, out-of-band egress, and the subsystem power path of Section 2.9; trust per OQ-52, Appendix C.7 |
| Regulatory | Subassembly approach, no FCC cert for v1 |
| Production BOM | ~$36 (100-qty) |

---

## 5. Hub Pro (LOCKED on ports and MCU; shares Standard base)

| Item | Decision |
|---|---|
| Ports | 8x RJ-45 8P8C, locking boot |
| MCU | ESP32-P4 (USB HS resolves the streaming bandwidth ceiling) |
| Protocol | Classical CAN at 500 kbps on the control pair, plus RS-485 streaming receivers |
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
| 12VHPWR Standard | Standard | INA240 per pin into ESP32-S3 ADC; + 2x NTC (connector temp) | 47k/10k divider into ESP32-S3 ADC | none | none (~+/- 1%, OQ-8 resolved) |
| 12VHPWR Pro | Pro | INA240 per pin into LTC2358-18 | 47k/10k divider into LTC2358-18 | RS-485 (pair 2) | local REF3033 |

The 24-pin uses the INA228 on all four rails (12V, 5V, 3.3V, 5VSB): 20-bit, 195 µV bus-voltage LSB, with hardware energy and charge accumulators. EPS and PCIe use the INA238: 16-bit, 3.125 mV bus-voltage LSB, no accumulators. Both share the same shunt scheme and the same 50 us minimum conversion (~20 kHz per-sensor ceiling), which clears the 10 kHz burst target.

The split is by limiting error source. The 24-pin's deliverable is fine voltage, which is ADC-limited, so it gets the INA228. EPS and PCIe deliver per-cable current totals, which are shunt-limited, so the INA238 is right-sized and its lower resolution and gain accuracy sit below the shunt floor anyway (Section 6.5). INA228 is used on all four 24-pin rails rather than only the 12V droop rail for two reasons: voltage resolution matters more on the 24-pin than anywhere else in the system, and droop on the 5V, 3.3V, and 5VSB rails is not yet characterized, so keeping 195 µV resolution on every 24-pin rail lets us detect and read that droop if it exists rather than designing it out. The accumulators come along on every 24-pin rail as a result, including complete 5VSB standby energy (energy scope is OQ-13).

The digital-sensor modules are self-referenced; only the 12VHPWR modules use a separate reference path, resolved locally on Pro (Section 3.3).

**Connector temperature sensing — 12VHPWR Standard (added v3.7).** The INA240 is a plain current-sense amplifier with no internal die-temperature sensor (unlike the INA228 on the 24-pin, whose die temperature supplies that module's temperature reading), so the 12VHPWR Standard module adds two NTC thermistors read through spare ESP32-S3 ADC2 channels — this module never uses Wi-Fi, so ADC2 is free and reliable. One NTC sits in the 12V power section by the shunt row, so it tracks the shunt and +12V-plane temperature that actually drifts the readings (and catches 12V-section overheating); one is an ambient reference at a cool board edge. Firmware reports absolute temperature and, more usefully, the rise above ambient (ΔT) — rise, not absolute, is the alarm. Its primary job is measurement quality and board health: the 1 mΩ shunt's TCR and the INA240's gain/offset drift both move with temperature, so the board reading lets firmware compensate the per-pin current (recovering the ~0.2 to 0.3% the shunt TCR would otherwise cost at this ~+/- 1% tier, OQ-8) and flags 12V-section overheating. It complements the per-pin current-imbalance read: imbalance is the leading indicator, temperature the confirming one. It also supplies the "temperature" datum the Appendix C.2 telemetry table lists for all tiers, which this module otherwise could not produce. (J4 is a soldered pigtail, so its GPU-side mate is off-board: that contact — the famous melt site — is NOT directly sensed. An NTC embedded in the pigtail's GPU plug, the only way to read it directly, was considered and DEFERRED (the module is board-only for now, v3.7); instead the GPU-side condition is inferred by fusing the board temperature with the per-pin current and the rail voltage. Revisit the smart-pigtail NTC if direct GPU-contact sensing is wanted.) No status LED is populated: this is an internal sensing board, not a visible product.

**12V input TVS — considered and declined (v3.7).** A transient-voltage suppressor across the 12V input was evaluated and rejected for this module. The INA240 carries a -4 V to +80 V common-mode rating, so rail transients do not threaten the sense front-end; the per-pin shunts are stressed by current (already sized for the 1.5 to 2x millisecond transient column, Section 6.3), not by rail voltage; and a power TVS on a ~50 A rail introduces a short-circuit failure mode worse than the transient it would guard against. If the one genuinely sensitive node — the 47k/10k divider tap into the ADC — is ever to be protected, that belongs as a small signal-level clamp on the tap, not a power TVS on the rail. Recorded so it is not re-litigated.

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

### 6.4 Shunt selection (LOCKED values, v1.2; 24-pin parts LOCKED v1.6, EPS/PCIe/12VHPWR parts PENDING per OQ-11)

Sized so max current plus transient stays inside the ADC range and dissipation stays manageable:

| Module / rail | Shunt | Drop / power at max | ADC range | LSB | Full scale |
|---|---|---|---|---|---|
| 24-pin 12V, 5V, 3.3V | 2 mΩ, Bourns CSS2H-2512K-2L00F | up to 40 mV / 0.8 W at 20A | +/-163.84 mV | 156 µA (INA228) | 81.9A |
| 24-pin 5VSB | 25 mΩ, Vishay WSK2512 R025 | 75 mV / 0.23 W at 3A | +/-163.84 mV | 12.5 µA (INA228) | 6.55A |
| EPS, per cable | 0.5 mΩ | 27 mV / 1.5 W at 55A | +/-40.96 mV | 2.5 mA (INA238) | 81.9A |
| PCIe, per cable | 0.5 mΩ | 20 mV / 0.8 W at 40A | +/-40.96 mV | 2.5 mA (INA238) | 81.9A |
| 12VHPWR, per pin | 1 mΩ | 12 mV / 0.14 W per pin | INA240A3 analog | ADC-set | per-pin |

The EPS and PCIe rows are one shunt per cable, identical and replicated across the module's cables. 24-pin 12V is 2-pin-limited to ~15A and may instead use the +/-40.96 mV range for finer resolution (about 39 µA per count on the INA228) if confirmed never to approach 20A. LSB shown is for the resident part (INA228 on the 24-pin, INA238 on EPS/PCIe); full scale is set by shunt and range and is identical across parts.

Shunt type: low-TCR metal-element / metal-strip precision shunt, tight tolerance, four-terminal Kelvin, power rating well above the dissipation above. Self-heating times TCR is the dominant thermal-accuracy error, and at 0.5 mΩ a few µΩ of tolerance or drift is a large fraction of the value, so the precision shunt is what protects accuracy at the low end. The temperature-induced current error is the product of TCR and self-heating rise, so a part wins by lowering either term; the locked 24-pin choice below lowers both. This supersedes the earlier v4 24-pin 5V and 3.3V values (which saturate the ADC above ~8A and ~3.3A and dissipate too much at 20A).

24-pin parts (LOCKED, v1.6, resolving the 24-pin portion of OQ-11). The three main rails (12V, 5V, 3.3V) use the **Bourns CSS2H-2512K-2L00F**: 2 mΩ, ±1%, four-terminal Kelvin, AEC-Q200, ±75 ppm/°C including copper terminals (the resistive alloy alone is ≤50 ppm/°C over 20 to 60 °C), inductance under 2 nH, 5 W on the recommended pad and 3 W on a conservative mounting. The value is unchanged, so the INA228 ADCRANGE and SHUNT_CAL scaling do not move. The ±1% initial tolerance is a fixed gain error trimmed out in the INA228 SHUNT_CAL register at calibration and so costs nothing in final accuracy; a ±0.5% grade exists for a board that ships without per-unit calibration. The win is on both temperature-error terms at once: TCR is about 3.3x lower than a commodity ±250 ppm 2512 part, and at 0.8 W the part runs near 16% of its 5 W rating (27% even on the 3 W figure), so self-heating rise is far lower for the same dissipation. The product cuts net temperature-induced current error by roughly an order of magnitude, with real derating margin.

The 5VSB rail keeps the **Vishay WSK2512 R025**: 25 mΩ, four-terminal Kelvin, in its low-TCR band (about ±35 ppm/°C), dissipating 0.225 W at 3 A (about 22% of its 1 W rating), with the 25 mΩ giving the fine LSB the standby-energy figure wants. The CSS2H series does not reach 25 mΩ, so 5VSB is the one rail where the WSK2512 is the right match. Mixing the two families across rails is fine.

EPS, PCIe, and 12VHPWR per-pin part selection stays open under OQ-11. The CSS2H series reaches 0.5 mΩ (±100 ppm/°C) and 1 mΩ (±75 ppm/°C, inductance under 2 nH) as natural candidates for the EPS/PCIe per-cable and 12VHPWR per-pin sites; the 1 mΩ part's sub-2 nH inductance is also the spec that bears on the Max module's HF and di/dt question (OQ-18). Not locked here.

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
| Control | Classical CAN, 500 kbps (pair 3) |
| Reference | Local REF3033 on module (ratiometric correction at the LTC2358-18) |
| Connector | RJ-45 8P8C, locking boot |
| Production BOM | ~$98 to $99 (100-qty) |

Cross-tier note: a Pro module in a Standard Hub runs CAN control and event telemetry normally; its streaming pair is connected at the jack but stays dark because the Standard Hub does not populate an RS-485 receiver. This is the intended graceful-degrade behavior.

### 6.10 Acquisition model: continuous sampling, ring buffer, and ALERT (LOCKED, v1.4; co-capture added v2.1)

The digital-sensor modules (24-pin, EPS, PCIe) run their INA228 or INA238 in continuous-conversion mode, and the MCU holds a per-sensor ring buffer of roughly 2 seconds of 1 kHz samples (about 2000 records per channel). The buffer is pre-roll: when a burst or event fires, the captured window already contains the lead-up held in the ring, which a read-on-event scheme cannot reconstruct. So both the part and the read loop run continuously; there is no idle-then-wake path for these modules.

Sampling and averaging: set each sensor's conversion time and averaging (AVG) so the part emits a clean averaged sample at the 1 kHz output rate rather than instantaneous snapshots decimated in firmware. This folds the part's faster internal conversions into each 1 kHz record, lowering noise and anti-aliasing the buffer. The ALERT limit comparison runs on that same averaged value, so threshold response is at the millisecond scale, which matches the 1 kHz record. Sub-millisecond transient capture is not reachable over I2C (OQ-9).

ALERT: the ALERT pin is the event trigger and the threshold detector, not an I2C load. Configure the limit registers (shunt over-voltage for current, power limit, bus over and under-voltage, temperature) so the hardware flags a crossing and raises ALERT, which the MCU uses to freeze and dump the ring buffer (pre-roll plus continued post-roll). Conversion-ready on ALERT also lets the MCU read once per finished conversion instead of polling for fresh data. Servicing an alert is a single DIAG_ALRT flag read per event.

I2C budget: 1 kHz continuous across the 24-pin's four channels sits near the full-round ceiling at 1 MHz (fast-mode plus), with headroom; at 400 kHz, trim the stored fields per sample to current and voltage. The energy and charge accumulators are read at the reporting interval, not the sample rate, so they add negligible traffic. Per-module ring-buffer memory (tens of KB) is trivial in the ESP32-S3 SRAM.

**Cross-module co-capture (v2.1):** A single module's trigger freezes every module's ring buffer, so any one rail's event captures the whole system on a common timeline. This is what makes a 24-pin droop legible against the PCIe or 12VHPWR surge that drove it, and for the CAN-only modules (24-pin, EPS, PCIe), which never stream, it is the only way to see a multi-rail transient at all. Mechanism, all tiers, over CAN, with no spare-pin hardware: on a local trip a module freezes and marks its buffer, then sends one high-priority broadcast FREEZE frame; every other module freezes in its CAN receive ISR and marks the same frame instant; the triggering module reports cause and timestamp over CAN; the host reads the frozen windows out and overlays them on the FREEZE instant; a broadcast re-arm frame follows readout. Alignment rides the fact that CAN is a simultaneous broadcast medium, so every node detects end-of-frame within about one bit time (a microsecond or two at 500k), far inside one 1 ms sample. Frame latency, a few hundred microseconds and worst case about half a millisecond under bus load, is absorbed by the 2 s pre-roll and does not affect alignment. The binding limit is readout rather than capture: a frozen multi-rail window returns over 500k classical CAN slowly (a 400 ms four-rail 24-pin window is roughly 6 kB and about 0.2 s; a full 2 s window approaches 1 s, and modules serialize on the one bus), so the default window is kept short, a few hundred milliseconds, and Standard is a clean single-event recorder rather than a back-to-back transient logger. A dedicated hardware trigger line is deliberately not used here. It earns its keep only for pinning an external event into the Max's MHz fast-capture buffer (Section 6.11), which is a Max-era decision weighed against pin 7's reserved 1-Wire identity path (Section 2.3). See OQ-27.

### 6.11 12VHPWR Max module (PROPOSED, exploratory, v1.6)

Status: proposed, not locked, captured for the decisions record. Sits above the Pro (Section 6.9) in the 12VHPWR tier stack; it is a module, not a Hub tier, and whether it implies a tier is OQ-15. Gating decisions are OQ-15 through OQ-21.

Role: top-end 12VHPWR module for continuous per-pin event classification, including micro-arc detection localized to the offending pin, plus on-demand waveform capture. The Standard does melt detection, the Pro adds per-pin precision and streaming, and the Max adds high-frequency event classification and capture, making the module a connector-health and condition-monitoring instrument rather than a meter. Target: builders and shops, IT and data-center operators, serious enthusiasts.

| Item | Decision (proposed) |
|---|---|
| MCU | ESP32-P4 with PSRAM |
| Per-pin DC / slow current | INA240A3 on the existing 1 mΩ per-pin shunt, into the Pro precision path (Section 6.9) |
| Per-pin HF event detect | AC-coupled tap across the same shunt into a bandpass plus envelope/RMS detector, one per pin, read continuously by a slow ADC |
| Full waveform capture | one fast ADC at ~10 to 20 MSa/s behind a 6:1 analog mux, trigger-driven, burst into PSRAM |
| On-board processing | FFT plus event classification on the P4 |
| Capture front-end bandwidth | ~2 to 5 MHz (arc-signature band) |
| Interconnect | 100BASE-T1 single-pair on pair 2 (proposed; diverges from Section 3.2, see OQ-20) |
| Connector | RJ-45 8P8C, locking boot |
| Indicative BOM | ~$140 to $170 (100-qty, estimate, not costed) |
| Indicative retail | $499 to $599 (target) |

Sensing architecture, three layers sharing the existing 1 mΩ per-pin shunt:
1. DC and slow precision (per pin): INA240A3 into the Pro precision path (Section 6.9), unchanged from the Pro. Magnitude, per-pin imbalance, slow-loop telemetry.
2. HF event detector (per pin, continuous): an AC-coupled wideband tap across the same shunt feeds a bandpass plus envelope/RMS detector, one per pin, read continuously by a slow ADC. This per-pin HF-energy value is the live arc and fast-event flag, and because it is per pin it localizes the event to a contact. At the arc band the shunt's parasitic inductance acts as a di/dt pickup, which helps catch fast edges. A couple of dollars per pin.
3. On-demand full capture (shared): one fast ADC at ~10 to 20 MSa/s behind a 6:1 mux. When a pin's envelope detector trips, that pin is switched in and its waveform is captured into PSRAM, then FFT'd and classified on the P4. Arcs are localized, so capturing the offending pin one at a time is acceptable.

The always-on layer is the per-pin energy; the fast capture is trigger-driven.

Bandwidth and the oscilloscope boundary: arc signatures are broadband current noise in roughly the few-kHz to ~1 MHz band, the region DC arc-fault detection uses. A ~2 to 5 MHz front end with captures at 5 to 10 MSa/s covers it with margin; the fast ADC at 10 to 20 MSa/s gives headroom. The front end is capped in the low MHz to classify the arc's electrical signature, not to chase plasma HF content that would add shielding and layout cost for no monitoring gain. The trigger-and-capture model delivers per-pin classification from cheap always-on detectors plus one shared fast channel; digitizing all six pins continuously at multi-MSa/s would need six fast ADCs or a high-end DAS and crosses into a six-channel scope front end (BOM past $200) for information the trigger model already provides. The Max stops short of that on purpose.

Per pin it monitors and classifies: magnitude and DC imbalance; VRM switching ripple and its spectrum (switching frequency, harmonics, effective phase count, phase-drop and phase-imbalance); transient di/dt on load steps with overshoot, droop, and ringing; AC ripple amplitude and per-pin ripple imbalance; micro-arc events localized to the offending pin; and over time a per-pin spectral health fingerprint, where new harmonics or broadband hash flag a developing fault before it becomes a melt.

Reconciliation notes:
- Interconnect diverges from the locked RS-485 (Section 3.2). The proposal is 100BASE-T1 on pair 2, requiring Hub-side 100BASE-T1 termination; power, CAN, and DETECT stay on their pairs. Ratification is OQ-20. The stated data flows (small continuous per-pin energy values plus features reported after on-module classification) are low-bandwidth and do not by themselves require 100 Mbps; the bandwidth case rests on on-demand upload of raw captured waveforms to the host, which OQ-20 should either make the explicit driver or else fall back to RS-485 or even classical CAN for feature-only reporting.
- The DC and slow precision plane reuses the Pro's INA240A3 path; whether it keeps the Pro's LTC2358-18 or a cost-reduced simultaneous ADC (for example ADS131M08) is OQ-21, since the HF and capture layers carry the fast work.
- It shares the 1 mΩ per-pin shunt; whether that element's HF and di/dt response is adequate or whether it needs a dedicated low-inductance element or a separate di/dt pickup is OQ-18. The CSS2H-2512K-1L00F (1 mΩ, inductance under 2 nH) is the candidate element (Section 6.4).
- DETECT: the Max uses the CAN + 100BASE-T1 comm-class code (Section 2.3), contingent on OQ-20; its category, exact type, tier, and serial come over CAN like every module, so it needs no new DETECT code.
- Graceful-degrade per Section 8: in a Hub without the matching link, the Max runs CAN control and event telemetry while its streaming and capture-upload pair stays dark, consistent with the Pro's behavior.
- Indicative BOM and retail are estimates, not locked, and the Max is deliberately not yet added to the production BOM table (Section 9) because it is exploratory.

### 6.12 SATA / peripheral power module (PROPOSED, exploratory, v1.8)

Status: proposed, not locked, captured for the decisions record. This module closes the platform's peripheral-rail blind spot, the SATA and Molex power that the 24-pin, EPS, PCIe, and 12VHPWR modules all miss. The headline use is SATA drives in NAS and enterprise arrays; the same rails carry Molex fans, pumps, and AIO gear. Gating decisions are OQ-22 through OQ-26.

Form: a powered SATA distribution board. It takes PSU peripheral power in, fans it out to drives over standard connectors, and senses each output. One CEC node per board, CAN-only, hot-pluggable like every module. This is the easy end of the sensing spectrum. Currents are low, dynamics are slow (spin-up is a 100 ms to 1 s envelope and health plays out over minutes to days), so integrated INA238 over I2C at 10 to 50 Hz covers it with no streaming link.

Tier diff:

| | Standard | Pro | Max |
|---|---|---|---|
| Role | total peripheral-power coverage, tidy distribution | per-drive health, predictive maintenance | per-drive health plus active power management |
| Current sensing | aggregate per rail | per-drive 12V and 5V, aggregate 3.3V | per-drive 12V and 5V, aggregate 3.3V |
| Voltage sensing | aggregate rail | per-drive (flags a sagging cable or connector) | per-drive |
| Sensors (8-drive board) | 3x INA238 | 17x INA238 (8 × 12V + 8 × 5V + 1 × 3.3V) | 17x INA238 |
| Power path | passive, shunts inline | passive, shunts inline | active, per-drive load switch |
| Staggered spin-up | no | no | yes |
| Remote per-drive power-cycle | no | no | yes |
| Failure risk added to drive power | negligible, shunts only | negligible, shunts only | a real inline failure point, mitigated by design |
| Buyer | wants total-power coverage and clean distribution | array owner wants to see which drive is failing | managed array wants sequencing and remote control |
| Relative BOM | low | medium | medium-high |

Per-drive current tracks drive health (spin-up current and time both climb as a drive degrades); per-drive voltage tracks connection health (a 0.4 V sag under load points at a corroded pin or a tired cable). Both readings come from the one INA238 on each rail, so the Pro's diagnostic value is nearly free once the board exists. Standard is the same board with only the aggregate sensors populated, which is genuine BOM differentiation rather than a firmware lock.

Input power (shared across tiers, and the part that makes the module viable): do not touch the PSU's proprietary modular peripheral port, and do not try to current-limit on a single SATA or Molex tap. Almost all the load is on 12V, and the one standard high-current 12V source on every modular PSU is the PCIe 8-pin, good for well over 20 A across its three 12V pins. Take 12V there. The 5V rail draws only about 5 to 8 A and is either passed through from a Molex or SATA input or regenerated on-board from 12V through a roughly 40 W buck (OQ-23). 3.3V is omitted by default. It is vestigial on modern drives, and presenting it can trip the SATA pin-3 PWDIS feature and keep a drive from spinning up, which is exactly why Molex-to-SATA adapters work universally. Offer 3.3V only as an option.

Output and fanout (shared across tiers): board-mount male 15-pin SATA power connectors, right-angle, the same part hot-swap backplanes use. A drive sitting at the board plugs straight on; a remote drive reaches it through a commodity female-to-male SATA power extension cable, the single most common SATA power accessory, in any length and right-angle variants. No custom cable appears anywhere in the chain. Spec molded wire-to-wire extensions and warn customers off the crimped-contact splitters that catch fire on 12V.

Reconciliation notes:
- DETECT: the CAN-only comm-class code (2.2k, Section 2.3) for all three tiers; category (power), exact type, tier, and serial come over CAN like every module.
- MCU: ESP32-S3-MINI-1 across all three tiers, the Max included, since its load switches are GPIO-driven and need no faster part. Module logic is 5VSB-powered over the RJ-45 like every module; the monitored drive power is the separate PCIe and Molex path.
- CAN-only, so the module is native in any Hub (Section 8) and nothing goes dark in a lower-tier Hub.
- Contributes the missing peripheral-rail branch to total-system energy (OQ-13).
- BOM and retail are not yet costed, and the module is deliberately not in the production BOM table (Section 9) because it is exploratory.

---

## 7. ARGB Controller (output module)

The ARGB Controller is the platform's first output module. It drives addressable 5V LED strips (WS2812 / SK6812 class) and is offered in three tiers by channel count: Standard at 8 channels, Pro at 16, Max at 32. Unlike the sensing modules of Section 6 it sources its own power, draws nothing meaningful from the Hub 5VSB rail, and presents on CAN for control and telemetry and on USB for standalone operation.

The differentiator is that the controller measures the LED load it drives and reports it. Every other ARGB controller, open or closed, is a blind fan-out that clocks data out with no knowledge of what is connected. Current sensing on the LED side, which is the platform's home turf, turns it into an instrument: it auto-detects per-channel LED count, runs a boot self-test with open / short / break detection, and reports total RGB power back to the Hub. That reported draw closes a real gap, because the RGB load lives on the peripheral 5V rail that no platform sensor otherwise sees (Section 7.6).

### 7.1 Tiers (architecture set; parts pending where noted)

| Tier | Channels | Power feed | LED current ceiling | Per-channel sensing | MCU |
|---|---|---|---|---|---|
| Standard | 8 | SATA 5V-direct, fat ganged cable | ~7A at 5V, shunt-enforced (working) | No (total only) | pending, see OQ-29 |
| Pro | 16 | PCIe 8-pin, 12V to buck | ~24A at 5V (working) | Yes | pending, see OQ-29 |
| Max | 32 | dual PCIe 8-pin, 12V to dual buck | ~48A at 5V, dual 16-ch rails (working) | Yes | pending, see OQ-29 |

Any tier works standalone over USB or integrated over CAN to any Hub. The module is CAN-only with no streaming link, so its graceful degradation is trivial: it runs CAN control and telemetry on any Hub, Standard through Mission Critical, with no tier-dependent link to lose (Section 8).

### 7.2 Power (Standard 5V-direct LOCKED; Pro and Max 12V buck, working basis)

Standard is 5V-direct with no buck (LOCKED). It takes 5V from a standard SATA power connector, but over a fat ganged cable that bonds the three 5V contacts to one thick conductor and the grounds to another, dropping the 12V and 3.3V wires. The SATA failure point is the thin daisy-chain wire and its crimps, which heat before the contacts do, so the fat cable removes the dominant problem and the three contacts share the load. At ~7A total that is about 2.3A per contact, roughly 1.5x the 1.5A nameplate, kept honest by the current shunt of Section 7.4. CEC ships this fat cable in the box. Input front end: a P-channel MOSFET for reverse polarity, a resettable fuse in the ~7A class, and a controlled inrush element (load switch or NTC) since there is no buck soft-start to slew the bulk-cap charge.

The controller derives its 3.3V logic from the same 5V feed (or USB VBUS when on USB alone, for bench flashing), so it presents negligible load on the Hub's RJ-45 VCC pin. This is deliberate: the SK6812 LED budget is the dominant lever in the total 5VSB cap of OQ-2, and the ARGB Controller moves all of that LED load onto its own SATA 5V, off the Hub 5VSB budget entirely.

Pro and Max take 12V and buck to 5V, because 16 and 32 channels exceed any safe 5V-direct feed. Working basis: Pro on a single PCIe 8-pin (150W on 12V), Max on dual PCIe 8-pin built as two independent 16-channel split-rail sections sharing one MCU. The feed choice, buck parts, phase count, and the single-versus-dual Max question are pending (OQ-35).

### 7.3 LED output stage (LOCKED approach)

A single 74AHCT244 octal buffer level-shifts all eight channels, scaling to two parts at 16 and four at 32. AHCT is chosen for its TTL input threshold (about 2V), so the 3.3V MCU drive is in spec at a 5V supply. The 74HC parts common in this class want about 3.5V to guarantee a high at 5V, so they ride on typical margin rather than the datasheet.

Per channel, after the buffer: a series resistor, a BAT54W dual Schottky as the DATA-first hot-plug clamp (it kills the powered hot-plug back-feed where a strip plugged in live back-powers its own controller through its protection diode), and a PESD5V0S1UL TVS for per-line ESD. The strip connector is the standard 5V VDG addressable header, three used positions on a keyed 4-position shroud. Automatic retention and anti-offset keying are carried as the mechanical layer (OQ-36).

### 7.4 Current sensing and self-description (the differentiator; LOCKED direction)

All tiers carry a total-rail shunt plus an INA180A2 amplifier into the MCU ADC. Pro and Max add per-channel sensing; the implementation and its BOM are pending (OQ-30). The single total-rail shunt is enough to deliver the headline features at calibration time by sequencing, that is, lighting one channel at a time and reading total current:

- Auto LED-count per channel. Light a channel all white at a known level, subtract the idle baseline, and divide by the per-LED current calibrated from a single lit pixel. The count populates without the user typing it. Honest limit: voltage droop down a long strip pulls far-pixel current down, so a long strip reads a little low and the figure is an estimate good to roughly five to ten percent on long runs, tighter on short ones.
- Boot self-test and fault localization. A sub-second sweep verifies every channel. An open draws nothing, a short draws too much. For a partial break, a cumulative sweep or a binary search (about eight steps on a 144-pixel strip) finds where the current stops stepping up, locating the break to within a pixel. Fault detection is high-confidence because a break is an order-of-magnitude current difference.

Real-time per-channel current during mixed operation needs the per-channel circuits of Pro and Max. Everything above rides the one shunt at calibration time, so the feature lands on the entry board. Bench validation of count accuracy, the localization method, and contact-health feasibility is open (OQ-32).

### 7.5 Communication and host integration (LOCKED approach)

The module is CAN-only in behavior: no RS-485, no streaming. Classical CAN at 500 kbps per Section 3.1, with the platform's CAN-FD deferred, so the Hub-path LED-streaming ceiling is bounded by classical CAN; whether that ceiling ever justifies revisiting FD for ARGB Pro and Max is carried under the platform's deferral (OQ-31, Section 3.1). Transceiver is the TJA1051T/3 per Section 3.1, with no module termination since the Hub holds the fixed 120 ohm split. DETECT (Section 2.3): the ARGB Controller is CAN-only, so it presents the existing CAN-only comm-class code (2.2k), and its type and tier ride CAN enumeration like every module, so no new DETECT code is added (OQ-6 resolved, v1.7). The RJ-45 is 8P8C FTP with locking boot per Section 2.1, and follows the consumer protection decision of Section 2.4: no per-pin PoE clamp, with the low-capacitance ESD diode on the DETECT pin.

USB-C is a data path, not a power feed. Open-software integration presents each channel as a zone, or all channels as one concatenated Adalight strip for the zero-driver case, with the firmware demultiplexing by the auto-detected per-channel counts so setup needs no manual LED entry. The paths are Adalight over USB CDC for a no-driver OpenRGB experience, a SignalRGB JavaScript plugin for the standard SignalRGB path, and optionally an upstream OpenRGB C++ driver for a native multi-zone device. Full-fidelity SignalRGB (per-LED canvas, audio and screen reactive) is the direct-USB path; over the Hub it is effect-offload by default with optional zone-resolution streaming, bounded by CAN bandwidth (about 30 kB/s usable on classical CAN, roughly 150 LEDs at 60 FPS only if the bus is otherwise idle). Integration commitment and ownership are open (OQ-33).

Control arbitration follows the platform LED pattern: the local USB source is default, and the Hub can preempt with CEC override priority for system events, including a safety alert surfaced as light (for example a 12VHPWR per-pin imbalance flashing the case before anything melts).

### 7.6 Telemetry and reporting (ties OQ-13)

The module reports total 5V current and power, the rail voltage at the SATA feed, per-channel inventory and health from the boot sweep, and per-channel current on Pro and Max. This is low-rate telemetry traveling up on CAN, which costs the bus almost nothing, in contrast to pushing LED frames down (Section 7.5).

The reported draw matters to the whole-system total because the RGB load sits on the peripheral SATA or Molex 5V rail, which no platform sensor taps. The 24-pin sees 5V only at the ATX connector; EPS, PCIe, and 12VHPWR do not touch peripheral 5V at all. So the ARGB Controller is the only window the platform has into that rail for RGB load, and reporting it stops the "all in" figure from understating by omission. The proposed peripheral SATA power module (Section 6.12) covers the same rail for non-RGB peripheral loads, so the two together close it. Aggregation into the system total is defined in OQ-34 and feeds the energy-scope decision in OQ-13.

### 7.7 Licensing and channel

Hardware under CERN-OHL-S v2. Firmware under Apache 2.0. Sold direct and through the CHH Shopify; not on Amazon.

---

## 8. Cross-tier compatibility

| Module \ Hub | Standard Hub | Pro Hub | Enterprise Hub | Mission Critical Hub |
|---|---|---|---|---|
| Standard module | Native | Works, Hub oversupplied | Works | Works, module is the weak link |
| Pro module | Works, streaming dark | Native | Native | Works |

Principle: a module never fails to function in any Hub. Higher-tier features go dormant when the Hub cannot service them, and activate without module replacement when moved to a capable Hub.

---

## 9. BOM summary (production, 100-qty)

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
| ARGB Controller Standard (8-channel) | ~$14 to $20 (electronics, preliminary) | Standard |
| ARGB Controller Pro (16-channel) | ~$35 to $50 (electronics, preliminary) | Pro |
| ARGB Controller Max (32-channel) | ~$70 to $100 (electronics, preliminary) | Max |

Note: the 24-pin ATX figure predates the v1.4 move to four INA228 parts; expect a modest increase over the INA238 baseline (the per-part premium times four). EPS, PCIe, and 12VHPWR lines are unchanged.

Note: the ARGB Controller figures are preliminary electronics estimates pending part selection (OQ-29, OQ-30, OQ-35). The anodized chassis, the automatic retention mechanism, and the magnetic base are a separate mechanical adder not included here (OQ-36).

---

## 10. Open questions (decisions needed; no assumptions made)

**OQ-1: Hub bulk power input (RESOLVED, v1.3).** The 24-pin module feeds the Hub over a dedicated 2-pin JST-XH 5VSB cable; the Hub then distributes 5VSB to downstream modules over their RJ-45 VCC pins. This removes aggregate current from any RJ-45 pin. The aggregate now sits on the JST-XH feed and the shared PSU 5VSB rail, governed by the total-current cap in OQ-2. See Section 2.5.

**OQ-2: Total 5VSB current cap.** Confirm a firmware cap on total CEC 5VSB draw (the SK6812 LED budget is the main lever) and the maximum LED state to budget for, sized so a fully populated system stays within the JST-XH rating and the shared 5VSB rail with margin. See Section 2.5.

**OQ-3: Precision reference path (RESOLVED, v1.1).** Local REF3033 on each Pro module; no distributed reference; pin 7 reserved as a spare. See Section 3.3.

**OQ-4: Cable length SKUs and policy.** What fixed cable lengths will be offered, and are Pro modules allowed on arbitrary user cables (accepting reduced reference accuracy under Path A) or restricted to characterized CEC cables? Interacts with OQ-3.

**OQ-5: RS-485 topology.** Confirm one receiver per Hub port (point-to-point) versus a shared multidrop bus across ports.

**OQ-6: DETECT encoding (RESOLVED, v1.7).** The pin-8 resistor encodes comm-class only (presence plus which link the Hub brings up on the port), pulled up through 10k to the Hub's 3.3V rail. Module category, type, tier, and unique serial move to CAN enumeration. Code table in Section 2.3: CAN-only (2.2k), CAN+RS-485 (4.7k), CAN+100BASE-T1 (10k), two reserved link codes, plus open (no module) and short (fault). The table is fixed-size and does not grow with module count.

**OQ-7: Document scope.** Should this document fully specify Enterprise and Mission Critical now, or keep them at platform-summary level until their first customer requirements land? The compute and OS direction for these tiers (the control-plane and data-plane split, an RTOS or FPGA-SoC, and the case for no Linux) is explored in Appendix B. Current leaning: an MCU or RTOS control plane plus an FPGA or TSN-switch data plane with no Linux, PolarFire SoC as the consolidated candidate (Appendix B.5).

**OQ-8: 12VHPWR Standard rail accuracy (RESOLVED, v3.7).** Accepted the ~+/- 1% ESP32-S3 ADC figure as the Standard-tier number, with NO local reference on this board. The Standard 12VHPWR is a transient-capture and per-pin-imbalance tool, not a precision instrument — it does not even sample its channels simultaneously (the ESP32-S3 SAR round-robins the analog channels), so a precision voltage reference buys little against the larger sampling and INL limits. The local REF3033 ratiometric path (to ~+/- 0.3 to 0.5%) stays a Pro+ feature: the precision buyer steps up to the 12VHPWR Pro, which carries the REF3033 and the LTC2358-18 simultaneous-sampling ADC. The Standard module's deliverable is connector-fault detection, which the v3.7 temperature-sensing addition (Section 6.1) targets directly, rather than rail precision.

**OQ-9: EPS/PCIe transient capture.** The INA238 averages, smoothing millisecond CPU/GPU transient spikes out of the reading. If transient visibility on bundled EPS and PCIe is wanted, that argues for the INA240-style fast analog path used on 12VHPWR, at the cost of the integrated I2C convenience. Decide whether bundled EPS/PCIe need transient capture or whether averaged total power is sufficient.

**OQ-10: Bundled-shunt vertical transition.** Lock copper coin versus filled-via field versus plated slot for the ~40 to 55A EPS/PCIe per-cable shunt sites, against cost and fab capability (see Section 6.7).

**OQ-11: Per-module shunt part selection (24-pin RESOLVED v1.6; EPS/PCIe/12VHPWR open).** 24-pin locked (Section 6.4): Bourns CSS2H-2512K-2L00F (2 mΩ, ±1%, ±75 ppm/°C including terminals, four-terminal Kelvin, AEC-Q200) on 12V, 5V, 3.3V; Vishay WSK2512 R025 (25 mΩ, ~±35 ppm/°C) on 5VSB. Still open: the EPS and PCIe per-cable (0.5 mΩ) and 12VHPWR per-pin (1 mΩ) parts, with final TCR, tolerance, package, and power rating. The CSS2H series reaches 0.5 mΩ (±100 ppm/°C) and 1 mΩ (±75 ppm/°C, inductance under 2 nH) as candidates; the 1 mΩ choice also bears on OQ-18.

**OQ-12: Per-module high-current stackup.** Lock the L3-rails-with-via-detour stackup versus the top-layer-rails alternative for each high-current module (see Section 6.7).

**OQ-13: Energy reporting scope.** The 24-pin INA228 provides hardware energy and charge on all four rails, including complete 5VSB standby energy, at no added cost. Decide whether energy reporting is scoped to that 24-pin standby and platform figure, or extended to total system energy, which needs energy on the load rails via firmware integration of the INA238 power reading on EPS and PCIe (and the LTC2358 path on 12VHPWR), summed at the host. The 24-pin energy is a partial figure and must not be presented as total. See the energy discussion behind Section 6.1.

**OQ-14: PoE / over-voltage protection scope (consumer RESOLVED v1.9; Enterprise/MC deferred to OQ-7).** Consumer (Standard and Pro): resolved. No per-pin PoE-grade over-voltage protection on the RJ-45 module interface, ratifying the board state, since that interface is internal and the 57V case is deliberate misuse rather than an accident (Section 2.4). A low-capacitance ESD diode on the DETECT pin (pin 8 into the ESP32 ADC) is locked separately for hot-plug (v2.0), distinct from the dropped PoE clamp. Enterprise and Mission Critical: the module RJ-45s inherit the consumer answer; the over-voltage question moves to whatever external uplink those tiers expose (today the optional 1000BASE-T1 host link, a separate connector) and is decided with the Enterprise/MC spec under OQ-7. This closes the divergence against the PCB repo (which had dropped the protection on Standard and Pro) and subsumes the repo's separate OQ-8 numbering.

**OQ-15: Max positioning.** Is the Max a new platform tier or a 12VHPWR module variant, and does it define its own Hub-tier requirements? Confirm the indicative BOM and the $499 to $599 retail target. See Section 6.11. The FPGA-versus-MCU question and the capture-FPGA shortlist are explored in Appendix B. Current leaning: MCU plus FPGA if the Max commits to full-fidelity per-pin capture, MCU-only ESP32-P4 otherwise, gated on OQ-20 (Appendix B.5).

**OQ-16: Arc-detection validation.** Validate the HF signature band and the bandpass-plus-envelope detector against real arcing on a degrading 12VHPWR contact. Set detection thresholds and confirm arcs separate cleanly from VRM transients and EMI, with controlled false positives.

**OQ-17: Fast-capture chain.** Lock the fast ADC (rate and bits), the 6:1 analog mux, and the wideband tap amplifier. Confirm achievable capture bandwidth and depth, and whether one shared fast channel suffices versus needing more for concurrent multi-pin events.

**OQ-18: HF sense element.** Decide whether the 1 mΩ 2512 shunt's HF and di/dt response is adequate for the arc band, or whether a dedicated low-inductance element or a separate di/dt pickup is needed per pin. Interacts with the 12VHPWR part choice in OQ-11 (the CSS2H 1 mΩ candidate is rated under 2 nH).

**OQ-19: Compute and memory.** Confirm the P4's on-board FFT and classification throughput at the expected event rate, size PSRAM for captures, and define the classification approach (feature extraction, thresholds, optional learned model) and the split between on-module computation and reported features.

**OQ-20: Max interconnect ratification.** The Max proposes 100BASE-T1 on pair 2, replacing RS-485 for this module and requiring Hub-side 100BASE-T1 termination, which diverges from Section 3.2. First pin the uplink requirement to an actual data flow: feature-only reporting fits RS-485 or even classical CAN, so 100BASE-T1 is justified only if on-demand raw-waveform upload to the host is a feature. Then ratify the per-module link and the Hub change, or retain RS-485 and accept its lower headroom.

**OQ-21: Precision-plane ADC.** Confirm whether the Max's DC and slow per-pin plane uses the Pro's LTC2358-18 (Section 6.9) or a cost-reduced simultaneous ADC (for example the ADS131M08), given that the HF and capture layers carry the fast work.

**OQ-22: SATA module positioning.** Confirm the Standard/Pro/Max ladder and the drives-per-board count, and set indicative BOM and retail. Decide whether the aggregate-only Standard is a worthwhile SKU or whether Pro is the entry point, given that the per-drive sensors are cheap once the board exists (Section 6.12).

**OQ-23: SATA input architecture.** Choose 5V pass-through (PCIe 12V plus a Molex or SATA 5V input, two input cables, staying on the PSU 5V rail) versus on-board 5V regeneration (PCIe 12V only plus a roughly 40 W buck, one input cable, off the PSU 5V rail). Confirm 3.3V is omitted by default for PWDIS compatibility (Section 6.12).

**OQ-24: SATA output connector.** Lock the board-mount male 15-pin power-only SATA part (right-angle), validate fit with commodity female-to-male extension cables, and set the bundle policy (whether common-length extensions ship in the box).

**OQ-25: Drive count and sensor scaling.** Set drives per board, confirm the INA238 I2C address and bus budget (16 addresses per part, two S3 I2C controllers), and define the crossover to a muxed external ADC for large arrays past roughly 32 sensors.

**OQ-26: Max active stage.** Lock the per-drive load switch (e-fuse versus discrete MOSFET), the staggered spin-up sequencing, the fail-safe behavior (fail-closed or bypass so a switch fault does not silently drop a drive), and whether to drive SATA PWDIS as a soft sequencing path alongside the hard switch.

**OQ-27: Cross-module co-capture details.** Lock the FREEZE frame's CAN ID and priority, the default and maximum capture window against the 500k readout budget, the re-arm and overrun policy (what happens to a second event arriving during readout), and the packed per-sample record format for readout. Confirm the deferred hardware-trigger option on pin 7 stays scoped to the Max's fast-capture alignment (Section 6.11) and is weighed against the 1-Wire identity upgrade (Section 2.3). See Section 6.10.

**OQ-28: Port-to-identity binding (poke-and-ack).** Lock the Hub-side per-port line-perturbation method (switchable pull-up versus brief drive) and the module-side high-impedance pin-8 tap, the sequence-versus-parallel discovery pattern and its timing, the CAN ack format, and the legacy-module fallback when a poke goes unanswered. Confirm the Pro RS-485 bring-up shortcut and the optional hot-plug per-port 5VSB current correlation as alternates. See Section 2.3. Hub hardware confirmed (v3.4 board): the four DETECT lines sit on dedicated ADC1-capable, bidirectional ESP32-S3 GPIOs (IO4-IO7) with per-port 10 kohm pull-ups, so the brief-drive method needs no added parts (reconfigure the port's ADC pin to a momentary push-pull output to perturb the line, then back to ADC to read), whereas a switchable pull-up would cost a per-port GPIO-controlled resistor -- leaning brief-drive on that basis. The board accommodates either; method, perturbation amplitude/timing, ack format, and discovery pattern are firmware-phase decisions.

**OQ-29: ARGB Controller MCU selection.** Three candidates with different strengths. RP2040 or RP2350 give parallel PIO output that scales cleanly to 16 and 32 channels and is the leaning for Pro and Max; the RP2350B (48 GPIO) is required at 32 channels since 32 outputs plus housekeeping exceeds the RP2040's 30 GPIO. ESP32-S3 is the platform-standard Standard-module MCU with native CAN (TWAI), giving codebase and BOM consistency, and drives 8 channels via RMT or the LCD/I2S parallel peripheral. A CH32V307-class part gives native classical CAN, USB high speed, and the lowest cost, and is what the main competitor uses. The 8-channel needs no parallel PIO, so a native-CAN part fits Standard well; the tension is a unified MCU family across tiers versus best-fit per tier. Decide unified or split. See Section 7.1.

**OQ-30: ARGB current sensing implementation and caps.** Confirm the Standard total-rail shunt plus INA180A2 firmware current-cap value on the fat-SATA feed (~7A working). For Pro and Max, lock the per-channel sensing approach (an analog current-sense amplifier per channel feeding the MCU ADC through an analog mux, versus per-channel sense ICs) and the resulting BOM. See Section 7.4.

**OQ-31: ARGB CAN class on Pro and Max.** The platform defers CAN-FD and runs classical 500k everywhere (Section 3.1). Decide whether the Hub-path LED-streaming ceiling on ARGB Pro and Max ever justifies revisiting that for these tiers, against the same constraints (FD-capable silicon, a control bus shared with sensing traffic, and the mixed-bus classical fallback). Default is classical, consistent with the platform. See Section 7.5.

**OQ-32: Current-sensed diagnostics validation.** Bench-validate auto-count accuracy against strip length and droop, the fault-localization method (cumulative sweep versus binary search), and whether header contact-health detection is feasible with total-only sensing or needs the per-channel path. See Section 7.4.

**OQ-33: Open-software integration path and ownership.** Commit to and validate the OpenRGB and SignalRGB presentation: Adalight over USB CDC for a zero-driver OpenRGB path (confirm against OpenRGB's current serial support), a SignalRGB JavaScript plugin, and optionally an upstream OpenRGB C++ driver. Decide channels-as-zones versus concatenated-strip and who maintains the plugin and driver. See Section 7.5.

**OQ-34: ARGB telemetry payload and Hub aggregation.** Define the reported fields (total 5V current and power, SATA-feed rail voltage, per-channel inventory and health, per-channel current on Pro and Max) and how the Hub folds the peripheral-5V RGB draw into the whole-system power total. Feeds OQ-13. See Section 7.6.

**OQ-35: Pro and Max power feed and buck.** Lock the 12V feed (PCIe 8-pin single on Pro, dual on Max versus single with a reduced cap), the buck parts and phase count, and the Max dual-16 split-rail topology. See Section 7.2.

**OQ-36: ARGB mechanical.** Lock the automatic retention mechanism (hinged comb versus per-port spring gate versus sliding plate, with anti-offset keying), the magnetic base and the adhesive steel witness plate for aluminum and glass mounting, and the anodized 6063 chassis with the backlit milled logo. Owner: Tyreke.

**OQ-37: Shielded (FTP) jack divergence (board-vs-spec; folded in from the repo fork, v3.2).** Section 2.1 locks FTP shielded jacks platform-wide, but the current prototype boards carry the unshielded Amphenol 54602 (LCSC C2847314) with grounded SH1/SH2 board-locks. Acceptable for prototype bring-up — the link carries CAN, 5VSB, DETECT, and Standard-dark RS-485, all shielding-insensitive. A non-magnetic metal-shell FTP jack is the production/EMC target. Hub Standard resolution (2026-06-05): the FTP MPN is locked to the Kinghelm KH-RJ45-58-8P8C (LCSC C2683360, single shielded 8P8C metal-shell right-angle TH), with its authoritative easyeda2kicad footprint origin-aligned to the existing 1.27 mm land (J2-J5 footprint cec:RJ45_FTP_Shielded_Horizontal now holds the Kinghelm geometry; contacts preserved, shell tabs as SH1/SH2). The original design reference was the Wuerth 615008137421 (C132217), declined because its real 1.02 mm contact pitch does not match the routed 1.27 mm land (full re-route) and stock is thin; the design-reference text is updated to the Kinghelm to match the as-built board. Modules + 24-pin rev2 still carry the unshielded 54602 — move them to the FTP part on their next rev. Pairs with the consumer PoE-drop in Section 2.4.

**OQ-38: Cadence and retention.** Lock the slow-telemetry rate, the spectral-snapshot interval, and the per-event capture-retention window against host and service storage and the link budget. See Appendix C.4.

**OQ-39: Feature-versus-raw collection.** Confirm features-by-default with on-demand raw-waveform pull as the collection model, and tie the raw path to the Max interconnect decision (OQ-20). See Appendix C.2.

**OQ-40: Outcome-label ingestion.** Decide how RMA, failure, and service events are tied to unit ID (manual builder entry, RMA-system integration, a builder portal), and the minimum label set a valid survivor selection needs. See Appendix C.3.

**OQ-41: Capture-context normalization.** Define the standard EOL load sequence and the field-context metadata required to compare captures, so a field reading is matched only against like conditions. See Appendix C.3.

**OQ-42: Population golden policy.** Decide the opt-in and anonymization model for any cross-account golden, and whether CEC offers a reference golden per popular config from opt-in data or stays strictly per-account. See Appendix C.1.

**OQ-43: Local-versus-service split and self-host parity.** Lock what must run on the Hub and bench offline (the EOL gate at minimum) and the parity requirement for the self-hosted service half. See Appendix C.5.

**OQ-44: Identity and provenance schema.** Define the unit-ID scheme, BOM-revision tagging, and the module-and-firmware inventory report the Hub emits at enumeration. See Appendix C.3.

**OQ-45: Telemetry ownership and residency.** State the data-ownership and retention posture for power telemetry, the deletion path, and the privacy boundary, consistent with the no-cloud stance and C.1.

**OQ-46: OS-side collector scope.** Define the host-app agent's collected event set per OS (Windows event log, ETW, WER, minidump fields; Linux EDAC, mcelog, dmesg, NVML, journald, kdump), the elevated-access model, and the mapping of event classes onto the outcome-label feed (item 3, OQ-40). See Appendix C.7.

**OQ-47: Cross-domain timebase.** Reconcile OS-event and NanoKVM timestamps against the Hub electrical timebase, and define event-triggered co-capture (an OS or electrical event annotating or triggering a Hub freeze and a NanoKVM keyframe), accepting that OS log timestamps are coarse and lag the fault. The wired Hub-to-NanoKVM UART (OQ-51) is the mechanism that places the NanoKVM's events on the Hub's local timebase directly. See Appendix C.7.

**OQ-48: NanoKVM in the data model.** Define the NanoKVM's reporting into Concierge (screen state, power state, captured failure screens), its use as the out-of-band egress when the host path is down, and whether it carries Hub flight-recorder data out in that case. The wired UART link (OQ-51) is the path by which the Hub hands its frozen flight-recorder window to the NanoKVM for that egress. Section 2.9 extends this to a fully dead system: a wall-wart into the NanoKVM USB-C powers the Hub and NanoKVM so the Hub's flash-persisted data egresses over the NanoKVM's network without opening the case. See Appendix C.7 and Section 2.9.

**OQ-49: NanoKVM screen-state classification.** Decide the screen-state classifier and stop-code OCR, the local or self-hosted vision model, and confirm the Alibaba DashScope path stays disabled, consistent with C.1 and the Latch Pro privacy posture. See Appendix C.7.

**OQ-50: Out-of-band trust and privacy boundary.** Set the privacy and trust boundary for OS crash data and NanoKVM visual capture (error metadata and screen state rather than content, customer-owned, self-host parity, user scoping), and the hardening required for the NanoKVM now that it sits in the fault-evidence path. See Appendix C.7.

**OQ-51: NanoKVM-to-Hub link form (form RESOLVED v3.7; baud and framed protocol firmware-open).** The physical link is locked: a reserved keyed **5-pin JST-PH** aux header on every Hub (vendored B5B-PH-K-S) carrying the full set of pins the NanoKVM exposes on its own header — the full-duplex 3.3V UART (TX/RX), the **shared 5V feed and ground** of Section 2.9, and the NanoKVM's **3.3V reference/presence** line (its two header grounds common at the connector). There is **NO trigger GPIO**: the NanoKVM exposes no drivable interrupt input, and the framebuffer-capture latency caps any fast-trigger benefit over a UART message anyway, so event triggers ride the UART in-band as a framed message. The link is power plus UART (no longer data-and-ground-only; the two boards now draw from one priority-OR'd rail per Section 2.9). The NanoKVM's 3.3V line is treated as an **untrusted** input, not a metrological reference: the Hub never relies on its absolute accuracy, and instead reads it through a divider on an ADC channel for presence (an open/absent line reads near 0 through the divider's lower leg) and validates it **ratiometrically against the Hub's own LDO-regulated +3V3**, read through an identical divider on a second ADC channel, so the ADC and divider error cancel in the ratio and a drifted or sagging NanoKVM rail is detected rather than believed. Still firmware-open: the baud (921600 working, matching the Teleplot tooling and giving headroom for window egress) and the framed message set (fault events in; keyframe request and frozen flight-recorder window out; heartbeat both ways; correlation IDs for co-capture alignment). See Appendix C.7 and Section 2.9.

**OQ-52: NanoKVM link trust boundary and egress arbitration.** Lock the untrusted-input handling (hardened bounded parser, an inbound allow-list of telemetry and rate-limited benign freeze requests, no privileged Hub control reachable from the link), and define how the via-Hub egress path dedups against the NanoKVM's own network path at the service so events are not double-counted. Consistent with the NanoKVM hardening in OQ-50. See Appendix C.7.

**OQ-53: Module-rail scope for the subsystem power feed.** Decide whether the module fleet rides the Section 2.9 shared 5V rail (whole-platform dual-feed, which frees on-board LED brightness on a maxed build by moving the operating draw to main 5V in S0) or stays on 5VSB-only with the discretionary loads (the ARGB strips, the NanoKVM, and capped on-board LEDs) offloaded individually. The lighter per-load path keeps the always-on monitoring core single-source and out of any source transition. The number that decides it is the S0 draw on a maxed build with the LEDs where you want them, against the main-5V headroom and the OQ-2 cap. See Section 2.9.

**OQ-54: External forensic power-in.** Confirm whether the NanoKVM's USB-C is externally accessible on the PCIe card in a closed case and accepts 5V in, since the card carries more than one USB-C and some are internal. If it is, the wall-wart path costs no CEC hardware; if not, or to cover builds with no NanoKVM, specify a CEC power-in port on a rear bracket that feeds the shared rail through the same OR and revives a Hub-only build for extraction. See Section 2.9.

**OQ-55: Source-OR part and back-feed isolation.** Lock the priority ideal-diode OR or priority mux (for example a TPS2116 or an LTC4412-class PowerPath, sized for the full subsystem current and low enough in drop) and verify the back-feed isolation on every source: that the Hub's 5VSB front-end Schottky is a series element in line (Section 2.7), that the NanoKVM's slot input is isolated, and that the wall-wart can never energize a dead PSU or motherboard. See Section 2.9.

**OQ-56: Persist-on-fault and hold-up sizing.** Define the Hub's persist-on-fault behavior (which critical events and frozen windows are written to the 16 MB flash as they occur, and the final flush on total power loss) and size the hold-up cap to cover both the source changeover and at least one flash write, so forensic recovery returns the data that mattered. See Section 2.9.

---

## Appendix A: Spare-pair / USB architecture exploration (explored, NOT adopted, v2.5)

This records a line of architectural exploration around the spare pin and a host bus, kept so the reasoning is on file and is not re-opened from scratch. The conclusion is that it is not adopted.

The chain. Starting from pin 7 as a single-ended spare (Section 2.3), the exploration asked what removing the DETECT sense entirely would allow, freeing pins 7 and 8 as a clean differential pair. The out-of-left-field use was USB on that pair, with the Hub acting as a USB hub so every module's USB rides the one cable and aggregates to the host. The natural completion was to make the Hub a USB host in its own right, on 5VSB, so the module-side USB bus is always-on and terminates at the Hub rather than the PC.

What it would add. Cabled, always-on firmware updates to any module with no physical access; host-direct debug and bulk (the ESP32 USB-Serial-JTAG and the existing Teleplot stream) surfaced through the Hub; and richer enumeration. With the Hub as host, those work with the PC off, the Hub becomes a standalone appliance, and USB becomes a real candidate to absorb DETECT (always-on, per-port, identity-rich enumeration) and the Pro-rate RS-485 stream (Hub-terminated), pointing at a leaner connector of power, CAN, and USB, with the streaming pair freed for Pro-rate modules. The Max's higher rate would still want a dedicated fast pair (100BASE-T1), so it does not fold in.

What it never changes. CAN stays under every version of this. Even a Hub-local USB host is master-slave and polled, so it cannot do the simultaneous peer broadcast the co-capture freeze depends on (Section 6.10), cannot give node-side priority arbitration for deterministic alerts, and is not an always-on peer control bus. CAN is fixed; a host bus could only ever be a second plane alongside it.

Why not adopted. The concrete near-term benefit motivating USB is firmware update, and firmware images are small enough that the update is short over the channels already present, so the payoff is modest. Against that, making the Hub a USB host plus internal hub plus a path back to the PC is substantial added firmware and silicon, worst on the cheap S3 Standard Hub whose single OTG controller cannot host modules and serve the PC at once. The settled architecture, a simple CAN control bus with RS-485 streaming added as a later layer, is the play. For the spare pin specifically, beefing up the sense-pin architecture (the dedicated Kelvin return for DETECT, Section 2.3) is the better use of effort than turning the pair into USB.

Status: not adopted. Held as a deliberate future fork if the operational case (fleet firmware management, a standalone-Hub appliance) ever outgrows the simple links.

---

## Appendix B: Compute tiers, FPGA versus MCU, and a Linux-free Enterprise (exploration, v3.0)

This records the compute-placement exploration for the Max and Enterprise tiers so the reasoning is on file. It is exploration, not a lock. It resolves against the processing-placement principle (Section 1) and feeds OQ-15 (Max) and OQ-7 (Enterprise).

### B.1 Why an FPGA on the Max, and what it buys over an MCU

An MCU executes instructions in sequence; an FPGA is reconfigurable fabric where many circuits run at once on every clock edge. The distinction is spatial parallelism and timing held in silicon rather than in software, and the Max's benefits all follow from it:

- Simultaneity. Independent per-pin capture pipelines sample on the same clock edge, so all six 12VHPWR pins are time-aligned. A muxed MCU front end samples channels at different instants and cannot give true per-pin correlation.
- Deterministic timing. A trigger in fabric fires on the next clock edge with nanosecond repeatability. An MCU response carries interrupt and scheduler latency measured in microseconds with jitter.
- Full-rate throughput. Six channels at 15 MSa/s is 90 Msample/s; a 400 MHz core has about nine instructions per sample with nothing else running, so an MCU must burst-capture and analyze afterward, bounded by its buffer. Fabric handles one sample per channel per clock in parallel and watches everything continuously.
- Wire-speed triggering and DSP. Filters, slope and window triggers, and a streaming FFT run on the live data and raise an event the cycle a condition is met, rather than after the fact.
- Hardware timestamping. A fabric counter off a disciplined oscillator stamps events to the clock period and serves PTP without OS jitter, which is what the sub-microsecond cross-module correlation needs.
- Concurrency without contention. Capture, trigger, timestamp, DMA, and the uplink run as separate circuits, none stealing cycles from the others.

Costs, stated honestly: HDL development and timing closure are a harder, slower skill than C firmware; irregular control flow (handshakes, parsers, config state machines) is natural on a core and painful in fabric; FPGAs cost more per unit, draw more (SRAM-based especially), and need config flash and extra rails; the IP ecosystem is more fragmented; and the analog front end (shunt, CSA, ADC) is external either way, so the advantage begins at the digital samples.

Conclusion: this is FPGA plus MCU, not FPGA instead of MCU. Fabric does the wide, fast, simultaneous, timing-critical work (capture, trigger, filter, timestamp, stream); a core does the sequential, high-level work (decide, report, configure). The FPGA is the physical form of the local-mandatory floor in the Section 1 principle, and the MCU keeps the movable part. SoC-FPGA parts put both on one die (Gowin GW5AST hard RISC-V, PolarFire SoC, Efinix with a Sapphire soft core).

### B.2 Max capture-FPGA shortlist

The Max FPGA is small to mid, because the architecture is stream-and-trigger, not buffer-everything: trigger detection runs continuously in fabric on the live stream (little memory), and only short windows are frozen to BRAM or external PSRAM/SDRAM on an event. That needs I/O for the parallel ADC lanes, a few dozen DSP blocks, and external memory the dev boards already carry.

- Gowin, via Sipeed Tang. Cheapest and fastest to prototype, on Amazon and AliExpress for tens of dollars. Sweet spot is the GW2A (Arora) or GW5A class (about 20K to 25K LUT4 with DSP and BRAM); the GW5AST adds a hard RISC-V core and nearly 300 DSP for capture and control on one die. Toolchain is Gowin EDA (license brokered by Sipeed), with partial open-tool support.
- Lattice ECP5 and the Nexus family (CrossLink-NX, Certus-NX). Mature, low power, and backed by a full open-source toolchain (Yosys and nextpnr via Project Trellis and Project Oxide), which fits the platform's FOSS stance and removes any vendor-license dependency for production builds. Strongest contender against Gowin.
- Efinix Trion and Titanium. Efficient, with a Sapphire RISC-V soft core to fold the controller into fabric, on the closed Efinity toolchain.
- AMD Spartan-7 / Artix-7. The mature default with the most DSP, but higher cost and a heavy Vivado install; likely more than a per-module Max needs.

Leaning: prototype on a Sipeed Tang in the GW5A class because it is immediately in hand; evaluate Lattice ECP5/Nexus for production on the open-toolchain argument.

### B.3 A Linux-free Enterprise (and Mission Critical)

Section 1 already places the Enterprise Hub on the ESP32-P4, not Linux. The Linux SBC (i.MX class) was a candidate, but the feature set does not require an OS, and avoiding one shrinks the networked attack surface, which matters most on the tier most likely to be air-gapped.

The enabling move is to separate the control plane from the data plane. The hard, high-bandwidth work (per-port gigabit switching, TSN scheduling, hardware timestamping) lives in a dedicated TSN switch IC or FPGA fabric and moves packets in hardware; the controller only configures and supervises it, never touching every packet. Configuring a switch needs a driver, not an OS. The rest of the feature set maps onto RTOS-class components: Zephyr or FreeRTOS; mbedTLS or wolfSSL for TLS (wolfSSL offers FIPS-validated builds, a cleaner certification target than a full distribution); MCUboot for signed OTA; littlefs for bounded timeseries storage; a discrete TPM or on-die secure block for the root of trust. The patchable surface becomes a handful of named libraries with no shell, no dynamic loader, no package manager, and no general-purpose scheduler adding jitter under PTP and TSN.

The standout part for the secure tiers is the Microchip PolarFire SoC: a hard 64-bit RISC-V cluster that runs bare-metal or RTOS rather than being forced onto Linux, flash-based (instant-on, lower power, no external bitstream to intercept, SEU-immune), with defense-grade security (PUF-protected key storage, DPA-resistant secure boot, an Athena crypto coprocessor with CAVP-certified and CNSA-compliant algorithms, anti-tamper, and an NCSC-reviewed design-separation flow), plus fabric for the deterministic switch and timestamping. It folds the OS-free secure controller, the data-plane fabric, and crypto into one device. The cost is real and Libero is heavy, so it is a high-tier part. This is consistent with Mission Critical already using a bare-metal Hercules safety coprocessor, so the top of the stack is already non-Linux.

Linux still wins only where the Hub must run arbitrary third-party software, containers, a real database, or a full web app. The Section 1 principle routes that work up to the host or self-host service layer (which can be Linux on the customer's own machine), so the Hub stays a lean appliance and does not need it. The reason the Hub can be Linux-free is the same reason it should be.

### B.4 Tooling and development effort (Claude Code for the HDL)

The B.1 development cost should be read with this mitigation. Claude is strong at common RTL and at verification (state machines, FIFOs, bus interfaces, FIR filters, and testbenches, where benchmark coverage is near-saturated), weaker on hard novel design (state-of-the-art models have topped out near a third pass rate on an expert-authored RTL benchmark), and weakest on the physical problems a basic simulation does not catch: timing closure, clock-domain crossing, and microarchitecture. Verilog is a low-resource language relative to mainstream software, so it is less reliable than the same model is at C or Python, and vendor-specific primitives (a Gowin or Lattice DSP or PLL block) want a datasheet check.

Claude Code is the multiplier rather than the raw model, because HDL is fully simulatable: the agent writes the RTL, writes a cocotb or Verilator testbench, runs it, reads the failures, and iterates until the bench passes, then runs Yosys and nextpnr and reads the utilization and timing reports. That turns plausible RTL into RTL that provably passes a defined bench, which is the main reliability lever. The open-source toolchain is fully headless and scriptable, so it is the most automatable, which converges with the FOSS reason the open-toolchain parts (Lattice ECP5/Nexus, Gowin's open flow) are already preferred: the open-toolchain FPGA is also the most agent-friendly one. The workflow is encoded in a custom skill or CLAUDE.md (coding standards, lint config, toolchain commands, reset and CDC conventions), with hooks forcing a lint-and-sim pass and a subagent for isolated CDC review; there is no official Anthropic FPGA skill, but the mechanism to build one exists.

The limit: passing simulation is necessary, not sufficient. Timing and CDC sign-off and board bring-up (real ADC timing, signal integrity, metastability) stay with the human and the hardware. Net effect on the decision: Claude Code substantially lowers the RTL and verification labor that historically deterred small teams from FPGAs, without removing the need for FPGA judgment on the physical problems, and it pairs best with the open-toolchain parts already on the shortlist.

### B.5 Current leaning

Max: MCU plus FPGA, conditional on OQ-20. If the Max commits to full-fidelity simultaneous per-pin capture, the leaning is an MCU for decide-and-report alongside an FPGA for capture, triggering, timestamping, and streaming, or a single SoC-FPGA such as the GW5AST that carries both. If the Max settles for trigger-and-report, the MCU-only ESP32-P4 path stands and no fabric is added. The FPGA, when present, is the physical form of the local-mandatory floor in the Section 1 principle.

Enterprise (and Mission Critical): an MCU or RTOS control plane plus an FPGA or TSN-switch-IC data plane, with no Linux. The control plane configures and supervises the switch and runs the API, TLS, OTA, and attestation on an RTOS; the data plane moves packets and timestamps in hardware. The consolidated candidate is the PolarFire SoC, one device holding an OS-free hard RISC-V, the deterministic fabric, and defense-grade crypto, chosen for the security and air-gap priority. This refines the Section 1 overview, which lists the Enterprise Hub on the ESP32-P4 as the simple baseline.

These are leanings, not locks, informed by the placement principle (Section 1), the FPGA-versus-MCU breakdown (B.1), the security reasoning (B.3), and the now-lower development cost (B.4). They feed the final decisions in OQ-15 (Max) and OQ-7 (Enterprise); the Max fabric remains gated on OQ-20.

---

## Appendix C: Concierge data collection (addendum, PROPOSED v1.1)

This addendum defines what the Concierge layer must collect, compute, and retain so the conformance, condition-monitoring, and fault-isolation system functions end to end: the golden-sample method, the cross-module co-capture freeze (Section 6.10), and the Max module's classification (Section 6.11). It is requirements capture, not a lock. It resolves against the processing-placement principle (Section 1) and feeds OQ-38 through OQ-50. "Concierge" here is the host-and-service layer: the host app on the PC plus the optional CEC-hosted or self-hosted service above it. v1.1 adds the OS-side and out-of-band visual vantage points (C.7), because the fault evidence the modules cannot see lives in the OS and on the NanoKVM that already ships in builds.

### C.1 Principle and ownership (the constraint everything sits under)

Concierge is the convenience layer over data the customer owns. The data path runs modules to Hub (timestamp and aggregate) to host app over USB to service, with no CEC infrastructure in the path; the AllMyStuff Cloudflare Tunnel and account routing carry it to the customer's own account or instance. Every collection and compute feature has a self-host equivalent, and the capability is identical when self-hosted. The CEC-hosted service sells convenience.

Two consequences are load-bearing for this system:
- The EOL pass/fail and the per-account golden must be computable locally, on the Hub and bench with no service connectivity, so a shop is never blocked by the network. The service makes managing goldens across configs and a fleet convenient; it is not required to clear a build.
- This is power and health telemetry, distinct from user content, so the "we can't see what your AI sees" posture holds. A golden is built only from an account's own units. Any cross-account or population golden is explicit opt-in and anonymized (OQ-42).

### C.2 What the platform can produce (source data, by tier)

This is the "what we can get" side. All of it originates at the modules and arrives through the Hub; tier sets what exists.

| Data class | Source | Rate / size | Notes |
|---|---|---|---|
| Slow telemetry | all tiers | per-second, small | per-rail V, per-rail and per-pin I, power, temperature, per-pin imbalance ratio |
| Energy / charge | 24-pin (INA228) | per-second, small | standby and platform energy; partial figure (OQ-13) |
| Transient captures | Pro, Max | event, bursty | frozen co-capture windows (Section 6.10): power spike, voltage droop |
| Spectral features | Max | periodic + on-change | ripple spectrum lines, switching frequency, effective phase count, harmonics |
| HF / arc events | Max | event | per-pin HF energy trend, arc event (time, pin, energy, class), optional captured waveform |
| Event log | all tiers | event | trigger fires, threshold crossings, classifications |
| AC fusion (optional) | external meter via host | per-second | efficiency, power factor, wall draw (the PSU efficiency exploratory concept) |

Per the processing-placement principle, the module ships features by default and raw waveforms only on demand. Concierge therefore collects features continuously and pulls raw captures when an event or a request warrants it. The on-demand raw-upload path is the live driver behind OQ-20.

### C.3 What Concierge must collect (required inputs)

Six categories. The first three are telemetry and labels, items 4 and 5 are the non-electrical vantage points (C.7), and item 6 is what Concierge computes from the rest. The ones easy to miss are the inputs that are not module telemetry: the outcome labels, and the OS and out-of-band feeds.

1. Identity and provenance. Unit ID, configuration and BOM revision, module and Hub inventory with tier and firmware version, build date, and account or builder ID. This is what groups units into a config so a golden can exist, and the BOM revision is the key the golden is versioned against (the lifecycle's restart-on-BOM-change).

2. Telemetry payload. The C.2 data, each capture tagged with its context: test-sequence ID at EOL, and operating state (load level, what the machine was doing) and ambient in the field. Two captures taken under different conditions are not comparable, so the context is a hard requirement rather than a metadata nicety.

3. Outcome labels. RMA events, failures, service actions, and unit disposition, tied to unit ID. This is the input most likely to be forgotten. Survivor selection is telemetry stability and a clean outcome together; the telemetry side is already collected, while the outcome side is a separate feedback channel the system does not work without. A golden cannot be built from "units that proved good" if nothing records which units proved good.

4. OS and host event data. The logical-fault record the modules cannot see: WHEA (machine checks, PCIe AER, ECC), bugchecks and stop codes, GPU TDRs and vendor codes (NVIDIA Xid, the AMD equivalents), Kernel-Power 41 (the OS-visible fingerprint of a hard power event), and application and device errors, with the Linux equivalents (EDAC, mcelog, dmesg, NVML, journald, kdump). Collected by a host-app agent (C.7). It is both a telemetry stream and an automatic source for the outcome labels of item 3, since a unit throwing corrected errors or resets is not a clean survivor.

5. Out-of-band visual and power-state data. From the NanoKVM (C.7): screen state and captured failure screens, stop codes, POST and boot status, and power and LED state, available when the OS is down. It is the witness for faults the OS agent cannot report, and it feeds the same fault-event and outcome-label streams.

6. Derived state. The golden band per config, the field envelope, per-unit deviation, trends, anomaly flags, and the current survivor set. Concierge computes these from categories 1 through 5 and holds them as derived state.

### C.4 Cadence and retention (PROPOSED)

| Stream | Cadence | Retention |
|---|---|---|
| Slow telemetry | continuous, per-second | long, downsampled for trend |
| Spectral features | snapshot at interval and on change | long |
| Triggered captures | per event | bounded window per event |
| EOL fingerprint | once at end of line | unit lifetime (it is the baseline) |
| Outcome labels | as they occur | unit lifetime |
| OS / host events | as they occur | unit lifetime |
| Out-of-band captures | on fault / on trigger | bounded per event |

The EOL fingerprint is the birth certificate and is kept for the unit's life because it is both the bench reference and the field-monitoring baseline. The capture-retention window and the snapshot interval trade against storage and the link budget (OQ-38).

### C.5 Where computation happens (placement)

This resolves against Section 1. On the module: capture and classification (Max). On the Hub: aggregation, the co-capture freeze, timestamping, local retention, and the local golden comparison that backs the EOL gate. On Concierge: population golden-building, trend and cross-unit inference, outcome correlation, the fault-signature library, and presentation. The split is the principle applied directly. The local-decision and offline-capable work stays low so the EOL pass/fail runs without the service, and everything whose result only ships upward or needs the population to mean anything moves to the service. Self-host parity means the service half runs on the customer's own instance with identical results (OQ-43).

### C.6 Golden-lifecycle data dependencies

This maps the collection requirements onto the lifecycle stages so nothing is missing at each step:
- Cold start needs only the absolute checks, which are local and need no golden, so a new config is covered from day one.
- Golden ready needs the longitudinal fingerprint (stability), the outcome labels (clean record), and a sufficient unit count.
- Build golden needs the stored EOL fingerprints of the selected survivors, averaged into a band and versioned to the BOM revision.
- Active and refine needs continued collection so the band tightens as the population grows, and the BOM-change trigger to retire a golden when the config revises.

### C.7 The three vantage points (electrical, logical, out-of-band visual)

The modules see the electrical domain only. Two further domains carry fault evidence the modules cannot reach, and the system fuses all three on one timeline. Each is blind to the other two.

- Electrical (modules and Hub). Rail and per-pin voltage, current, transients, ripple, and arc energy, per C.2. Always-on through 5VSB. In-band egress is the host USB path; out-of-band electrical egress is the networked Hub (the Max-tier direction).
- Logical (the OS-side agent, item 4). The logical-fault record: WHEA, bugchecks, GPU TDRs and vendor codes, Kernel-Power 41, and application and device errors, with the Linux equivalents. Collected by a host-app agent with elevated read access. It is the only vantage point on logical faults, and it works only while the OS is alive and the agent is running.
- Out-of-band visual and power state (the NanoKVM, item 5). The NanoKVM, shipping today as CEC Access, is a separate Linux SoC with its own network, the HDMI framebuffer, USB HID, and a front-panel-header tap for power and the power and disk LEDs. It is the vantage point that works when the OS is dead. It captures the BSOD screen and its stop code even when the OS never wrote a dump, the POST and BIOS error screens of a machine that will not boot, and the difference between a frozen frame, a no-signal, and a black screen, none of which the OS agent can report because there is no OS to report them. It reads power and LED state out-of-band, corroborating a hard reset from outside the machine, and it can act, capturing evidence and then power-cycling and watching the POST. AllMyStuff is the brain and the NanoKVM and modules are the limbs.

The gap the NanoKVM fills is specific: the OS agent goes silent exactly when a fault is worst, a hang, a bugcheck before the dump is written, or a board that will not POST. The NanoKVM is the witness across that gap, and because it has its own network it is also the out-of-band egress when the host path is down. On a build with a NanoKVM and a USB-only Standard or Pro Hub, which is what ships now, it is the only out-of-band channel, so the out-of-band half of this system is already partly deployed.

Two integration points and one constraint:
- Keyframe trigger. The us_ax layer's on-demand keyframe (us_ax_request_key_frame) lets an electrical or OS trigger pull a synchronized screenshot of the screen state at the moment of the event, aligning the visual capture to the electrical timeline.
- Screen-state classification. Vision on the framebuffer can classify the screen (normal, BSOD, POST error, frozen, no signal) and OCR a stop code into a structured fault event, out-of-band. This must run locally or self-hosted under the C.1 posture, with the device's default Alibaba DashScope endpoint staying disabled. It is convenience-not-capability applied to vision: the classification is the feature, and the privacy-preserving version self-hosts the model.
- Honest limit. The NanoKVM sees only the HDMI output, so a GPU that stops outputting reads as no signal rather than a rendered error, and a separate networked witness is a separate attack surface, which is why its existing hardening (enforced auth, rotated credentials, the deferred kill switch, no Alibaba path) matters more once it sits in the fault-evidence path.

Wired Hub link (adopted in intent; form pending OQ-51 and OQ-52). Beyond the network path, a dedicated full-duplex UART joins the NanoKVM to a reserved aux header on the Hub, coupling the visual and electrical vantage points locally, below the network and the service. It does two things the network path cannot. It lets the Hub timestamp the NanoKVM's fault events on its own electrical timebase as they arrive on the wire, so the two domains share one local clock rather than being reconciled from coarse, lagging, network-delivered timestamps at the service (OQ-47). And wired both directions, it lets the Hub hand a frozen flight-recorder window to the NanoKVM to egress over the NanoKVM's own network when the host USB path is down, which gives the USB-only Standard and Pro Hubs an out-of-band escape they otherwise lack (OQ-48). Because the NanoKVM is the networked, separate-attack-surface element, the Hub treats the link as untrusted telemetry-in and benign-requests-in (a freeze request is harmless and rate-limited), never as a privileged control channel, with a hardened bounded parser and a data-and-ground-only wire that keeps the two boards independently powered. The link is reserved on every Hub and sits idle when no NanoKVM is wired in, and it layers over the network fusion rather than replacing it, so it is an enhancement rather than a single point of failure. The benefit is inverted by tier: the USB-only Standard and Pro Hubs gain the most, since this is their only out-of-band escape, while Enterprise and Mission Critical already have their own egress and mainly gain the tight local fusion. The connector and pin set are now locked (v3.7): a reserved keyed 5-pin JST-PH aux header carrying the full-duplex 3.3V UART (TX/RX), the shared 5V feed, ground, and the NanoKVM's 3.3V reference/presence line — the full set of pins the NanoKVM exposes on its header. There is no fast trigger line: the NanoKVM exposes no drivable interrupt input and the framebuffer-capture latency would cap its benefit anyway, so triggers ride the UART in-band. The UART parameters and framed protocol stay firmware-open under OQ-51, and the trust boundary and egress-path arbitration are OQ-52. Section 2.9 supersedes the data-and-ground-only framing above: the same reserved aux header and cable also carry the shared 5V power feed, so the inter-board link is power plus UART and the two boards are no longer independently powered but draw from one priority-OR'd rail. That feed is what lets the Hub power the NanoKVM in normal operation and, in reverse, lets a wall-wart through the NanoKVM power the Hub for forensic recovery from a fully dead system.

---

## 11. Revision history

- **v3.7 (this revision, 2026-06-05):** resolved the **NanoKVM aux-link form** (OQ-51). The link is locked to a reserved keyed **5-pin JST-PH** aux header (vendored B5B-PH-K-S) on every Hub, carrying the full set of pins the NanoKVM brings out on its own header: the full-duplex 3.3 V UART (TX/RX), the **shared 5 V feed and ground** of Section 2.9, and the NanoKVM's **3.3 V reference/presence** line. There is **no trigger GPIO** — the NanoKVM exposes no drivable interrupt input (and framebuffer-capture latency caps a fast trigger's benefit anyway), so event triggers ride the UART in-band as a framed message; this simplifies the header and resolves the OQ-51 trigger-line question. The baud (921600 working) and the framed message set stay firmware-open. The change corrects a momentary mis-read that the NanoKVM exposed only UART/GND/3V3: it does also expose **5 V + GND**, so the Section 2.9 shared monitoring rail and the wall-wart-through-NanoKVM forensic-recovery path are confirmed and stand unchanged. Updated Section 2.9, the Section 4 NanoKVM aux-link row, OQ-51, and Appendix C.7; no other board or architecture change. (An interim v3.7 draft that had mistakenly made the link UART-only — dropping the shared 5 V and routing forensic power through a Hub rear jack — was reverted before this entry; the shared rail is the correct design.)
- **v3.7 (this revision, 2026-06-05):** added connector temperature sensing to the 12VHPWR Standard module (Section 6.1) and resolved OQ-8. The INA240 has no die-temperature sensor (unlike the 24-pin's INA228), so the module gains two NTC thermistors into spare ESP32-S3 ADC2 channels — one at the J3 +12V connector pins (the on-board melt site), one ambient — reporting temperature and ΔT-above-ambient, the direct read of the contact-resistance failure mode. It complements the per-pin current-imbalance read (imbalance leads, temperature confirms) and supplies the Appendix C.2 "temperature" datum this module otherwise could not produce. Resolved OQ-8: the Standard tier accepts the ~+/- 1% ESP32-S3 ADC figure with no local reference — it is a transient-capture / imbalance tool, not a precision instrument (no simultaneous sampling), and the REF3033 precision path stays a Pro+ feature. Declined a 12V input TVS (the INA240's +/- 80 V common-mode rating, current-not-voltage shunt stress, and a 50 A-rail short-failure hazard make it net-negative) and a status LED (internal board, not a visible product). Board work: the two NTC dividers were spliced into the routed 12vhpwr-standard schematic (ERC clean, netlist-verified TEMP1->IO13 / TEMP2->IO14, every existing UUID preserved so the PCB link is intact); test points stay a GUI add if room allows. No other board changed. Scoped **board-only**: a pigtail/GPU-plug NTC for the off-board GPU contact was considered and deferred; the on-board NTCs are for shunt-TCR / INA240-gain drift compensation of the per-pin current + 12V-section overheat, with the GPU side inferred by fusing temperature with current and rail voltage. Placement intent moved from the J3 connector pins to the shunt row.
- **v3.6 (2026-06-05):** consolidated the canonical v3.4 upload (the subsystem-power / NanoKVM / Concierge architecture branch, forked from the shared v3.1 baseline) into this board-reconciled line. Adopted the upload's new architecture: **Section 2.9 (subsystem power management, PROPOSED)** — a hardware priority ideal-diode OR across three 5V sources (PSU main 5V tapped downstream of the 24-pin 5V sensor, 5VSB, and a wall-wart through the NanoKVM USB-C) feeding one shared monitoring rail, reconciled onto the **as-built TPS2121 front-end mux** (Section 2.7) which it extends from two inputs to three, with firmware sensing the live source and setting the load budget and mode rather than switching its own supply (which would deadlock the MCU), back-feed isolation on every source, a forensic-recovery path (a wall-wart powers the Hub and NanoKVM so flash-persisted data egresses over the NanoKVM's network without opening the case), and persist-on-fault flushing to the Hub's 16 MB flash; **Appendix C (Concierge data collection, PROPOSED v1.1)** with its three-vantage-point fusion (electrical modules and Hub, the OS-side logical agent, and the out-of-band NanoKVM visual and power-state witness on one timeline); and the **NanoKVM aux-link** table row (reserved keyed header, 3.3 V UART plus the shared 5 V feed) on Hub Standard, inherited by Hub Pro. Renumbered the upload's OQ-37 through OQ-55 to **OQ-38 through OQ-56** to avoid collision with this line's OQ-37 (the shielded-jack divergence, resolved to the Kinghelm KH-RJ45-58), and placed them in Section 10. Overrode rather than imported the upload's stale board facts — TJA1462A → TJA1051T/3, ESP32-S3-MINI-1-N16R2 → ESP32-S3-WROOM-1-N16R8, the discrete 1 Ω inrush plus SS14 front end → the TPS2121 mux and D1, aluminum-polymer → aluminum-electrolytic hold-up, M2.5 → M3 mounts — keeping this line's as-built v3.2 through v3.5 decisions. No board change; this aligns the canonical document with both branches.
- **v3.5 (2026-06-05):** locked the CAN transceiver to the classical **TJA1051T/3** (high-speed CAN, VIO = 3.3 V, LCSC C38695), replacing the TJA1462A platform-wide. The TJA1462A was carried only to keep the CAN-FD door open, but FD is deferred platform-wide (v2.0), so the FD/SIC part is unwarranted: TJA1051T/3 is cheaper (~$0.40 vs ~$1.02), far better stocked (~121k vs ~166), pin-compatible SO8, and fully covers the locked 500 kbps floor and the optional 1 Mbps. One consequence: TJA1051T/3 is NOT a SIC (ringing-suppression) part, so the optional 1 Mbps now rests solely on the Section 3.1 bench SI test passing on the passive star/stub topology with no transceiver-side help (the 500 kbps floor is unaffected); if 1 Mbps is ever needed and marginal, a SIC transceiver run classical is revisited for that option. Propagated to every board that has the transceiver: Hub Standard U2 (sourced 2026-06-05) and all six generated module schematics (atx-24pin + rev2, eps-8pin, pcie-8pin 2-/3-port, 12vhpwr-standard — U2 value → TJA1051T/3, LCSC C38695, ERC clean on each), plus the gen-modules.py default. Hub Pro and 12VHPWR Pro have no CAN transceiver placed yet, so they inherit the lock when built out. Also retargeted the Section 2.4 consumer-PoE rationale to the TJA1051T/3's own CAN bus-pin protection.
- **v3.4:** added an optional bus-wide 1 Mbps CAN rate to Section 3.1. 500 kbps stays the default and the locked floor and CAN-FD stays deferred; the whole shared bus may instead run classical CAN at 1 Mbps, never per-module or per-tier, since one TJA1462A on one CAN_H/CAN_L net with one split termination is a single-bitrate medium. The driver is bandwidth where CAN is the only pipe — about halving the Section 6.10 frozen-window readout and about doubling the Section 7 ARGB-over-Hub headroom — so Standard, the only CAN-only tier, gains most. It is firmware-only: the TJA1462A (CAN-SIC) and both TWAI controllers already do 1 Mbps and the Hub CAN front-end is unchanged, so the sole gate is the Section 3.1 star/stub signal-integrity bench test, now to be run at 1 Mbps. Negotiation is Hub-led auto-baud with TWAI error-counter fallback to 500 kbps; a DETECT-code bitrate advertisement was considered and declined (it costs a module resistor, grows the locked DETECT table, and buys nothing since every module is already 1 Mbps-capable while the real variable is per-install SI, which DETECT cannot sense). Board reconciliation (2026-06-04, Hub Standard pre-fab review): completed the v3.2 §2.7 fold-in — the v1.1 discrete 1 ohm 1 W inrush resistor and separate reverse-polarity diode are now explicitly marked superseded by the TPS2121 mux (soft-start inrush + source-side reverse blocking), which the Hub Standard table had still listed; and recorded that D1, the reverse-isolation Schottky, is built as SB120 (1 A/20 V) with SS14 (40 V) noted as a higher-margin drop-in. No design decision changed — this aligns the document with the as-built board.
- **v3.3:** locked the 24-pin module dual-feed rule in Section 2.7. The 24-pin is both the bulk 5VSB source (JST feed) and a module on a Hub RJ-45 port; with its RJ-45 VCC commoned on +5VSB it paralleled the JST. Because the Hub power-mux sits only in the JST leg (JST at the mux input, RJ-45 VCC at the output), a short RJ-45 patch makes the RJ-45 the lower-resistance path — overloading the 1.5 A RJ-45 contact near full load and bypassing the mux's OR-ing. Decision: the 24-pin's RJ-45 VCC pin (J1.1) is no-connect (the module self-powers from its own 5VSB tap), so all bulk flows over the JST as OQ-1 intends; GND/CAN/DETECT unchanged. The fix lands on 24-pin rev3; the ordered rev2 carries the parallel path, with the prototype-run mitigation and the Hub-side workaround options captured in the board docs.
- **v3.2:** reconciled against the CEC PCB-repo fork, folding in the locked board decisions this document's branch had not carried. Added Section 2.8 (module PSU-side interposer cabling: the 24-pin's two Molex Mini-Fit Jr male headers and the female-to-female bridging-cable SKU; the 12VHPWR soldered connectors). Corrected the Section 4 Hub Standard MCU from the non-existent ESP32-S3-MINI-1-N16R2 to the **ESP32-S3-WROOM-1-N16R8** (the MINI-1 has no 16 MB SKU; antenna keepout honored). Corrected the 4700 µF hold-up cap from "aluminum polymer" (unobtainable at this value) to **aluminum electrolytic** (Panasonic EEVFK1C472M, 16 V). Moved the corner mounts **M2.5 → M3** to match the PC fastener standard. Added the Hub Standard front-end architecture to Section 2.7: a TPS2121 PSU/USB priority mux, a reverse-isolation Schottky feeding an isolated +5V_HOLD hold-up reservoir for a blackout telemetry dump, and a ~470 µF surge cap on the +5VSB distribution rail, designed so the hold-up storage never smooths the measured 5VSB. Recorded the shielded-jack board divergence (boards carry the unshielded Amphenol 54602 against the Section 2.1 FTP lock) as OQ-37, and marked the Mini-Fit Jr → RJ-45 re-cut action item complete. No upload-side decision was changed.
- **v3.1:** added Appendix B.4 on FPGA development tooling and B.5 on the current compute leaning. B.4 records that Claude Code lowers the RTL and verification effort flagged in B.1 through a simulate-iterate loop (write RTL, write a testbench, run it, fix, then synthesize and read timing reports), is strong on common RTL and verification and weak on timing, CDC, and microarchitecture, and is most automatable on the open toolchain, which converges with the FOSS choice, while simulation passing stays necessary but not sufficient before hardware sign-off. B.5 records the leaning: MCU plus FPGA on the Max if it commits to full-fidelity per-pin capture (gated on OQ-20, MCU-only otherwise), and a Linux-free MCU-or-RTOS control plane plus FPGA-or-switch data plane on Enterprise and Mission Critical, with the PolarFire SoC as the consolidated candidate. Reflected the leaning in Section 1, OQ-7, and OQ-15.
- **v3.0:** added Appendix B, the compute-tier exploration for the Max and Enterprise. Broke down what an FPGA provides over an MCU on the Max (true per-pin simultaneity, cycle-deterministic triggering, full-rate continuous DSP, hardware timestamping, contention-free concurrency) and the honest costs (HDL effort, poor fit for control flow, BOM and power, ecosystem), concluding it is FPGA plus MCU, with fabric doing the local-mandatory capture-and-reduce work of the Section 1 principle. Listed the capture-FPGA shortlist (Gowin via Sipeed Tang, Lattice ECP5/Nexus on an open toolchain, Efinix, AMD; PolarFire SoC for secure tiers) and a Linux-free Enterprise path via a control-plane and data-plane split with an RTOS stack (Zephyr, wolfSSL FIPS, MCUboot, littlefs) or a PolarFire SoC. Exploration only; feeds OQ-15 and OQ-7, both cross-linked.
- **v2.9:** recorded the processing-placement principle in Section 1, a design rule for how much computation each tier should carry. A device keeps only the processing that bandwidth or autonomy forbids moving up (the reduction needed to fit its uplink, and any decision it must make faster than a round trip or while the next layer is absent); everything else moves to a higher layer where compute is amortized, context is system-wide, and updates land once. The corollary is to spend bandwidth before silicon. This gives OQ-15, OQ-20, and OQ-7 an explicit baseline instead of being re-argued each time.
- **v2.8:** recorded the DETECT pull-up reference rationale in Section 2.3. The pull-up goes to the Hub's local 3.3V rather than the available 5VSB because the ESP32 and S3 ADC cap near 3.3V, so an open port at a 5V reference would over-range the ADC and stress a non-5V-tolerant pin; 5VSB is also a looser, noisier reference that the bandgap-referenced ADC cannot compensate; and a 5V line would break the pin-8 module sense tap behind poke-and-ack. The wider code span a 5V reference would buy is not needed, since identity is on CAN and the comm-class table is small and fixed.
- **v2.7:** added Section 7, the ARGB Controller, the platform's first output module, in three tiers (Standard 8-channel, Pro 16, Max 32). Standard is locked to 5V-direct over a fat ganged SATA cable with a shunt-enforced ~7A cap; Pro and Max are 12V-to-buck on a working basis. Its differentiator is the measure-and-report stance: a total-rail current shunt on every tier (per-channel on Pro and Max) drives auto LED-count, a boot self-test with break localization, and total RGB power reported to the Hub, closing the peripheral-5V gap in the whole-system total alongside the proposed SATA module (Section 6.12). Reconciled the uploaded draft to the current baseline: CAN-only classical per Section 3.1 with the draft's per-ARGB CAN-FD question reframed under the platform deferral, no new DETECT code since type and tier ride CAN (OQ-6 resolved, against the draft's premise of adding codes), and consumer protection per the resolved Section 2.4 decision (no PoE clamp, ESD diode on DETECT, against the draft's "subject to OQ-14"). Renumbered the draft's OQ-15 through OQ-22 to OQ-29 through OQ-36 to continue the global sequence, shifted the former Sections 7 through 10 up by one, and added three preliminary BOM rows. Firmware Apache 2.0, hardware CERN-OHL-S v2.
- **v2.6:** added the port-to-identity binding mechanism to Section 2.3, resolving the limitation that DETECT maps a port to a link class but not to a unique module. The Hub pokes one port's DETECT line, the module on it senses the poke on a high-impedance pin-8 tap and acks over CAN with its serial, and the Hub binds serial to port, which keeps identity on CAN and the code table fixed so it spends no namespace. Added the compatibility clause that the current prototype modules lack the pin-8 tap and so will not respond to a poke even on a Hub built with the feature, with the Hub falling back to today's known-but-unbound behavior for any tapless module. Noted the Pro RS-485 bring-up shortcut and the hot-plug per-port 5VSB current correlation as alternates. Opened OQ-28.
- **v2.5:** added Appendix A, capturing the spare-pair / USB / Hub-as-USB-host exploration as a thought record and marking it not adopted. The settled architecture stands: a simple CAN control bus with RS-485 streaming as a later layer. USB's main near-term draw is firmware update, which is short anyway, and making the Hub a USB host plus hub plus PC bridge is more effort than it is worth, worst on the cheap S3 tier. The spare pin is better spent beefing up the DETECT sense (the Kelvin return, Section 2.3) than turned into USB. Held as a deliberate future fork only if fleet firmware management or a standalone-Hub appliance case ever outgrows the simple links.
- **v2.4:** recorded two rationale notes. Section 3.2 now states why RS-485 stays as the streaming lane rather than folding into a host bus: it terminates at the always-on Hub rather than the PC (keeping the Hub a timestamping aggregator, not a passthrough), gives each port a dedicated free-running pipe with no host scheduling, and is where the high-rate future (100BASE-T1 for the Max) lives, which Full Speed over Cat5e cannot reach; it is flagged as the link most worth re-examining if a host bus were ever made always-on and Hub-terminated. Section 2.3 now states that enumeration is host-independent: identity rides CAN on 5VSB, so the Hub enumerates with the PC off, and a sense line or host bus only adds the per-port physical mapping needed for streaming bring-up, which only matters when the host is present.
- **v2.3:** recorded the rationale for CAN as the control bus rather than a host bus like USB (Section 3.1). CAN is multi-master, peer, broadcast, multi-drop, and alive on 5VSB with no host, and those properties are what the co-capture freeze (one frame to every module simultaneously, no host in the loop) and always-on monitoring through standby, boot, and shutdown depend on, none of which a single-host polled bus can provide. Noted that a host bus on the spare pair would complement CAN as a firmware, debug, and enumeration channel rather than replace it, and that host-independent enumeration stays on CAN by module announcement at power-up.
- **v2.2:** recorded the pin-7 spare-line exploration as a note in Section 2.3. No use adopted. The one concrete gain identified is a dedicated Kelvin return for the DETECT divider, removing the shared-ground IR-drop error term and scaling in value with cable length (OQ-4), which trades against keeping pin 7 signal-capable for the deferred Max trigger and would need a per-port pin 7 to allow both. Logged the uses considered and set aside as redundant (1-Wire identity and EEPROM, a hardware power-state line, out-of-band firmware recovery, a second comm channel or redundant power pin), each already covered by CAN, the MCU MAC, module flash, the 5VSB-always-on power order, or the JST-XH bulk feed. Pin 7 stays reserved.
- **v2.1:** added cross-module co-capture to the acquisition model (Section 6.10). Any one module's trigger now freezes every module's ring buffer, so a single rail's event captures all rails on a common timeline, which is the only way the CAN-only modules (24-pin, EPS, PCIe) can see a multi-rail transient since they never stream. Implemented over CAN as a high-priority broadcast FREEZE frame, firmware-only on every tier, with no spare-pin hardware and no respin: CAN's simultaneous broadcast gives sub-sample inter-module alignment (about a bit time, a microsecond or two at 500k), and the few-hundred-microsecond frame latency is absorbed by the 2 s pre-roll. Noted that readout, not capture, is the Standard limit and that the default window stays short to keep readout sub-second. Corrected the prior turn's framing that a hardware line was needed for alignment; the dedicated trigger is now scoped only to pinning an external event into the Max's MHz fast-capture (Section 6.11), a Max-era decision against pin 7's 1-Wire identity reservation. Opened OQ-27.
- **v2.0:** walked the control-plane CAN back to classical 500 kbps on every tier and deferred CAN-FD (Section 3.1). Neither MCU runs FD in silicon (the ESP32-S3 TWAI is classical only; the ESP32-P4 TWAI is also classical and treats FD frames as errors), so FD would mean an external MCP2518FD on every Pro node, while RS-485 already carries the streaming, leaving the CAN control plane light enough for 500k classical. Classical also keeps the shared bus uniformly compatible, since a classical-only Standard module on an FD bus would corrupt it, so mixed builds force classical anyway. Kept the CAN-FD-capable TJA1462A so the option stays open, and scoped any future FD to a concrete large-transfer or Enterprise node-count need under OQ-7. Propagated the change through the Section 2.2 note, the Hub Pro and 12VHPWR Pro tables, and the Max interconnect notes. Locked the low-capacitance DETECT-pin ESD diode on every Hub and module, separate from the dropped PoE clamp (Section 2.4, OQ-14).
- **v1.9:** resolved OQ-14 for consumer tiers. Standard and Pro carry no per-pin PoE-grade over-voltage protection on the RJ-45 module interface, ratifying the board state, since that interface is internal to the PC and a 57V PoE injection means deliberate misuse rather than an accident; the realistic accident (an ordinary network jack) is covered by the TJA1462A's own CAN bus-pin protection, and dropping the VCC series resistor returns its drop to the 5VSB budget (Section 2.4). Recommended a low-capacitance ESD diode on the DETECT pin for hot-plug as a separate, cheaper decision from the PoE clamp (locked in v2.0). Reframed the Enterprise and Mission Critical half: the module RJ-45s inherit the consumer answer, and the over-voltage question moves to whatever external uplink those tiers expose (today the optional 1000BASE-T1 link), deferred to the Enterprise/MC spec under OQ-7. The earlier platform-wide protection requirement is retired.
- **v1.8:** added the proposed SATA / peripheral power module as Section 6.12 (exploratory, not locked), closing the peripheral-rail blind spot the 24-pin, EPS, PCIe, and 12VHPWR modules all miss. It is a powered SATA distribution board, CAN-only, ESP32-S3, sensing with the INA238 at 10 to 50 Hz, in a Standard (aggregate per rail) / Pro (per-drive 12V and 5V sensing) / Max (per-drive sensing plus active per-drive load switches for staggered spin-up and remote power-cycle) ladder, with the diff chart in Section 6.12. Input takes 12V from a PCIe 8-pin to avoid the PSU's proprietary peripheral port and the single-tap current limit, 5V passed through or regenerated, and 3.3V omitted by default for PWDIS compatibility. Output is board-mount male 15-pin SATA with commodity female-to-male extensions to the bays, no custom cable. Opened OQ-22 through OQ-26 for its gating decisions and noted that it contributes the peripheral-rail branch to OQ-13.
- **v1.7:** resolved OQ-6. DETECT is demoted from a full module-type/tier code to a comm-class sense: the pin-8 resistor encodes only presence and which link the Hub brings up on the port (CAN-only 2.2k, CAN+RS-485 4.7k, CAN+100BASE-T1 10k, two reserved, plus open for no-module and short for fault), pulled up through 10k to the Hub's 3.3V rail rather than the 5VSB VCC so the divider stays in the ADC range. Module category, exact type, tier, and unique serial (the module MCU MAC) move to CAN enumeration, an unlimited namespace, so the code table is fixed-size and does not grow as modules or categories are added (Section 2.3). Noted the per-port-class-not-serial limitation and the 1-Wire EEPROM upgrade path if per-port unique identity is ever needed. Updated the Max module note to use the CAN+100BASE-T1 comm-class code.
- **v1.6:** resolved the 24-pin portion of OQ-11. The three main rails (12V, 5V, 3.3V) lock to the Bourns CSS2H-2512K-2L00F (2 mΩ, ±1%, ±75 ppm/°C including copper terminals, four-terminal Kelvin, AEC-Q200, inductance under 2 nH), confirmed against the Bourns datasheet, and 5VSB keeps the Vishay WSK2512 R025 (25 mΩ). The value is unchanged, so INA228 ADCRANGE and SHUNT_CAL scaling are untouched, and net temperature-induced current error drops about an order of magnitude through lower TCR and heavier derating (Section 6.4). EPS, PCIe, and 12VHPWR per-pin parts stay open under OQ-11. Added the proposed 12VHPWR Max module as Section 6.11 (exploratory, not locked): per-pin continuous HF event detection with arc localization, a shared trigger-driven fast-capture channel, on-board FFT and classification on an ESP32-P4 with PSRAM, and a proposed 100BASE-T1 interconnect that diverges from the locked RS-485 (Section 3.2). Opened OQ-15 through OQ-21 for its gating decisions, with OQ-20 flagged to pin the uplink to an actual data flow before adopting 100BASE-T1. Fixed a stale Section 3.3 reference that still named the INA238 on the 24-pin (now INA228).
- **v1.5:** reconciled against the CEC PCB-repo ground-truth spec (GitHub, 2026-05-30). Adopted the Standard-module MCU lock: the 24-pin, EPS, PCIe, and 12VHPWR Standard modules run the ESP32-S3-MINI-1, the same family as the Hub Standard (Section 1). Added Section 2.7 (Hub bulk power input) with the dedicated 2-pin feed's keying and front-end landing, folding in the repo's fuller detail. Recorded the PoE divergence: the repo and current boards drop per-pin over-voltage protection on Standard and Pro, reversing the Section 2.4 requirement; this document holds the requirement and opens OQ-14 to ratify or reverse rather than inheriting the board state. Logged the reconciliation actions the PCB side owes this document: adopt the INA228 on the 24-pin (pin-compatible with the repo's INA238, no respin), correct 12VHPWR Standard from a single-rail INA238 to six per-pin INA240 into the ESP32-S3 ADC (a board change if built single-rail), state EPS and PCIe sensing as per-cable rather than a single 12V rail, and import the current-handling domain (Sections 6.2 to 6.8), the acquisition model (Section 6.10), the reference resolution with pin-7 reservation, and OQ-8 through OQ-13.
- **v1.4:** the 24-pin moves to the INA228 on all four rails (12V, 5V, 3.3V, 5VSB) for fine bus-voltage resolution, both to capture 12V droop and to detect any uncharacterized droop on the 5V, 3.3V, and 5VSB rails; EPS and PCIe stay on the INA238. Added the acquisition model (Section 6.10): continuous-conversion sensors, a per-sensor ~2 s ring buffer of 1 kHz samples with pre-roll, averaging tuned to the 1 kHz output rate, and ALERT as both the threshold detector and the buffer freeze trigger. Opened OQ-13 (energy reporting scope), noting the 24-pin now carries hardware energy and charge accumulators on every rail. The 24-pin BOM figure is flagged as predating the part change.
- **v1.3:** OQ-1 resolved. Hub bulk power is a dedicated 2-pin JST-XH 5VSB feed from the 24-pin module, with 5VSB distributed to downstream modules over their RJ-45 VCC pins; Section 2.5 rewritten so the aggregate current sits on the JST-XH feed and the shared 5VSB rail rather than any RJ-45 pin; OQ-2 broadened from an LED cap to a total 5VSB current cap.
- **v1.2:** added the module current-handling domain (Section 6): sensing-granularity policy (per-rail on 24-pin, per-cable on EPS/PCIe, per-pin on 12VHPWR), an over-spec current-target table, a production shunt-selection table (superseding the v4 24-pin shunt values), ADC-range and resolution characterization, a no-heatsink thermal stance (copper plus chassis coupling), high-current layout and stackup guidance, and the Kelvin locality rule. Opened OQ-9 through OQ-12 (EPS/PCIe transient capture, bundled-shunt via transition, shunt part selection, per-module stackup). Platform sections (interface, CAN/RS-485, Hub tiers) unaffected; EPS/PCIe sensor counts unchanged and now stated explicitly as per-cable.
- **v1.1:** precision reference resolved to a local REF3033 on each Pro module, no distributed reference, pin 7 reserved as a spare (OQ-3 closed); v4 current-sensing absorbed (INA238 on 24-pin/EPS/PCIe, INA228 as the 20-bit option, INA240 retained on both 12VHPWR tiers, LTC2358-18 on Pro) with a production sensing summary added (Section 6.1); v4 sensing sheet superseded on reference distribution, DETECT, and pin-7 allocation; 12VHPWR Standard accuracy opened as OQ-8.
- **v1.0:** established as platform ground truth. RJ-45 8P8C locked across Standard and Pro with locking boot; Mini-Fit Jr retired; DETECT defined as analog single-wire ID and presence sense; Hub Pro fixed at 8 ports; control confirmed entirely on CAN with RS-485 for streaming only; connector current understanding corrected; precision-reference and bulk-power decisions opened.
- **Prior threads reconciled:** v1.1 Hub Standard (Mini-Fit Jr), v3 architecture (RJ-45), v4 sensing (INA238).
