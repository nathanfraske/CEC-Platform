# CLAUDE.md

Operating guidance for Claude Code working in the CEC platform repository.

## Ground truth and precedence

`CEC-Platform-Ground-Truth-Spec.md` is the canonical specification and holds
precedence over everything else, including this file. Where this file and the
spec disagree, the spec wins, and this file should be updated to match. Treat
this file as a working summary plus operating instructions, and read the spec
before making any design decision.

Spec revision reflected here: v3.4 (2026-06-03).

v3.2 reconciliation (2026-06-03): the repo spec was merged with the user's
canonical v3.1 upload. Operate by these net changes: (1) CAN is CLASSICAL 500k on
EVERY tier — CAN-FD is deferred platform-wide (was "FD on Pro"). (2) PoE /
over-voltage is RESOLVED for consumer — Standard/Pro carry NO per-pin PoE clamp
(ratified), and a low-capacitance ESD diode on DETECT pin 8 is LOCKED on every
Hub and module (Hub Standard now populates it as D2-D5; modules + 24-pin rev2
still pending — action item). (3) The open-question
list is now OQ-1..OQ-37; the shielded-jack divergence moved to OQ-37. (4) New
spec scope now in play: the ARGB controller (§7), the proposed 12VHPWR Max
(§6.11) and SATA (§6.12) modules, and the compute/FPGA exploration (Appendix B).
Read the spec before acting on any of these.

## What this project is

CEC is a modular PC power-telemetry system. Per-rail sensing modules connect to
a central Hub over a single commodity cable (RJ-45). The Hub aggregates
telemetry and forwards it to the host PC over USB. Four tiers (Standard, Pro,
Enterprise, Mission Critical) are built from one fundamental design with
progressively populated features. Modules are tier-agnostic and degrade
gracefully: any module works in any Hub, with higher-tier features going dormant
when the Hub cannot service them and activating without replacement when moved
to a capable Hub.

## Repository layout

```
cec-platform/
  lib/                       # shared library: the locked universal interface
    cec.kicad_sym            # symbols
    cec.pretty/              # footprints (RJ-45 FTP jack, SK6812, ESP32, power input; per-pin protection net dropped for consumer (§2.4), Enterprise/MC uplink protection under OQ-7)
    3dmodels/
  hubs/
    hub-standard/
    hub-pro/
    hub-enterprise/          # platform-summary only for now (OQ-7)
    hub-mission-critical/    # platform-summary only for now (OQ-7)
  modules/
    atx-24pin/
    eps-8pin/
    pcie-8pin/
    12vhpwr-standard/
    12vhpwr-pro/
  fab/                       # tagged release snapshots of exactly what was sent to the board house
  scripts/                   # kicad-cli wrappers and CI helpers
  CLAUDE.md
  .gitignore
```

The universal-interface parts (the RJ-45 jack, the SK6812 chain, the ESP32
module, the power input — plus the optional Enterprise/MC over-voltage protection
network, now consumer-dropped per §2.4 with Enterprise/MC under OQ-7) live in `lib/` so a change propagates to every board instead of
being redrawn per board.
Use project-relative library paths (`${KIPRJMOD}`) in `sym-lib-table` and
`fp-lib-table`. Never commit absolute library paths.

## Boards

| Board | Directory | Tier | MCU | Ports | Host link | BOM target (100q) |
|---|---|---|---|---|---|---|
| Hub Standard | hubs/hub-standard | 1 | ESP32-S3-WROOM-1-N16R8 | 4 | USB Full Speed | ~$36 |
| Hub Pro | hubs/hub-pro | 2 | ESP32-P4 | 8 | USB High Speed | ~$45 |
| Hub Enterprise | hubs/hub-enterprise | 3 | ESP32-P4 + secure element | n/a | USB HS (+ optional 1000BASE-T1) | ~$50 |
| Hub Mission Critical | hubs/hub-mission-critical | 4 | ESP32-P4 + crypto | n/a | redundant uplinks | ~$80 |
| 24-pin ATX module | modules/atx-24pin | Standard | ESP32-S3-MINI-1 | - | - | $35* |
| EPS 8-pin module | modules/eps-8pin | Standard | ESP32-S3-MINI-1 | - | - | $32 |
| PCIe 8-pin module | modules/pcie-8pin | Standard | ESP32-S3-MINI-1 | - | - | $38 |
| 12VHPWR Standard module | modules/12vhpwr-standard | Standard | ESP32-S3-MINI-1 | - | - | $49 |
| 12VHPWR Pro module (lead) | modules/12vhpwr-pro | Pro | ESP32-P4 | - | - | $98 to $99 |

Every board uses the RJ-45 connector defined below. Enterprise and Mission
Critical are specified at platform-summary level only until first customer
requirements land (OQ-7); the Enterprise tier additionally carries an RJ-11 trust
channel and a secure element, and Mission Critical adds redundant power, CAN, and
trust.

*The 24-pin $35 target predates the v1.4 move to four INA228 parts (spec §8);
expect a modest increase over the INA238 baseline. Revisit once shunt parts
(OQ-11) and the INA228 line cost are quoted.

## Locked decisions (do not change without explicit instruction)

These are settled in the spec. Do not alter them, and flag any schematic,
layout, or BOM that contradicts them.

Connector and physical interface:
- Module-to-Hub connector is RJ-45 (8P8C) for all tiers, all modules, all Hubs.
  Mini-Fit Jr is retired as the module-to-Hub interconnect and as the Hub
  bulk-power connector platform-wide. (It is NOT banned from a module's PSU-side
  power path: the 24-pin ATX module legitimately uses Molex Mini-Fit Jr headers
  there — that is the ATX standard connector, spec §2.8. See below.)
- Locking-boot RJ-45 is the default shipped variant. Mechanical-keyed variants
  remain available for high-security deployments. Shielded (FTP) jacks on Hub and
  modules.
- Shielded-jack divergence (OQ-37, renumbered v3.2): spec §2.1 LOCKS shielded
  (FTP) jacks platform-wide. Hub Standard now assigns the shielded FTP footprint
  (cec:RJ45_FTP_Shielded_Horizontal) on J2-J5 (2026-06-04) — pad-for-pad identical
  to the old Amphenol 54602 land, so it drops onto the existing placement/routing.
  REMAINING GATE before fab: lock the exact shielded MPN (Wuerth 615008-series
  horizontal, non-magnetic, is the reference) and confirm/adjust the SH1/SH2 +
  mounting-peg geometry to it — the prepared footprint mirrors the 54602's two
  side board-locks, and some shielded jacks instead ground via a rear post or add
  front shield fingers. The standalone modules + 24-pin rev2 still carry the
  UNSHIELDED 54602 (LCSC C2847314); that is COMPATIBLE, not a conflict — a shielded
  Hub jack with unshielded module jacks terminates the cable shield at one end only
  (the Hub: SH1/SH2 -> GND/chassis), which is the preferred single-end grounding,
  and the link is shielding-insensitive anyway (CAN + 5VSB + DETECT + Standard-dark
  RS-485). Modules move to FTP on their next rev.
- PoE/over-voltage protection (RESOLVED for consumer, spec §2.4 v2.0): Standard
  and Pro carry NO per-pin PoE-grade over-voltage protection on the RJ-45 module
  interface — the board state is RATIFIED (internal interface; 57V PoE injection
  is deliberate misuse; the realistic non-PoE network-jack accident is covered by
  the TJA1462A's own CAN bus-pin protection). This closes the consumer half of
  OQ-14. SEPARATELY LOCKED (v2.0): one low-capacitance ESD diode on the DETECT pin
  (pin 8 -> ESP32 ADC) on EVERY Hub and module, for hot-plug insertion ESD on the
  bare analog input. Hub Standard now populates this pin-8 ESD diode — D2-D5,
  PESD5V0S1UL in SOD-323, one per port, cathode to each DETECT line and anode to
  GND (added 2026-06-04, verified ERC/netlist). The generated standalone module
  schematics (EPS/PCIe/12VHPWR-Std) now carry it too — D1 = PESD5V0S1UL via the
  generator, regenerated 2026-06-04 (footprint assigned at layout); the ordered
  24-pin rev2 PCB still ships without it (rev3 picks it up). Enterprise/MC
  over-voltage attaches to their external uplink, deferred to OQ-7.
- Connector must have a documented current rating of at least 1.5A.
- Hub bulk power comes in on a dedicated 2-pin +5VSB power-in connector, separate
  from the RJ-45 interface, fed from the 24-pin ATX module; the Hub then
  distributes 5VSB to its ports over the RJ-45 VCC pin. Locked for every Hub
  (resolves OQ-1). RJ-45 VCC therefore carries per-port distribution only, not
  the trunk. Use the simplest 2-pin part rated for the full Hub trunk with margin
  (working selection: 2-pin JST-XH, >=3A); never Mini-Fit Jr.
- 24-pin RJ-45 VCC is NO-CONNECT (LOCKED, spec §2.7 v3.3): the 24-pin module is
  both the bulk 5VSB source (JST feed) and a module on a port, so its own RJ-45
  VCC pin (J1.1) is left open — NOT tied to its +5VSB — so all bulk flows over
  the JST, not in parallel over the RJ-45 VCC. The Hub mux sits only in the JST
  leg (JST = mux input, RJ-45 VCC = mux output), so a short patch would otherwise
  make the RJ-45 the lower-R path: it would hog the bulk current on the 1.5A
  contact and bypass the mux. Other modules' RJ-45 VCC stays connected (their only
  5VSB source). Fixed on 24-pin rev3; the ordered rev2 carries the parallel path
  (prototype mitigation + Hub-side workarounds in the board docs).

Module PSU-side power-path connectors (spec §2.8, LOCKED v1.6 — distinct from the
RJ-45 module-to-Hub interface above):
- 24-pin ATX module is a power-path interposer with TWO Molex Mini-Fit Jr (5569)
  24-circuit MALE headers: input J3 (PSU side) and output J4 (motherboard side).
  No board-mount FEMALE 24-pin ATX receptacle exists as a standard part, so both
  module connectors are male, the same gender as the motherboard header. The
  PSU's own (female) cable plugs onto J3 directly; the run from J4 to the
  motherboard needs a dedicated FEMALE-TO-FEMALE 24-pin ATX bridging cable (a
  female receptacle on each end, since J4 and the motherboard are both male
  headers), supplied by CEC as a platform SKU. Convention: board headers are
  male, the inserting cable end is female. Both J3 and J4 are the Molex 5569
  right-angle male footprint — do not "fix" one to female.
- 12VHPWR modules (Standard and Pro) solder their 12VHPWR (12V-2x6) connector(s)
  directly to the board (board-mounted); no detachable pass-through header and no
  bridging cable. On the melt-prone high-current connector this removes a
  mated-contact pair from the power path.

Pin allocation (LOCKED; DETECT encoding resolved v1.7):

| Pin | Cat5e pair | T568B color | CEC function | Tiers |
|---|---|---|---|---|
| 1 | Pair 1 | White-orange | VCC (+5VSB power) | All |
| 2 | Pair 1 | Orange | GND (power return) | All |
| 3 | Pair 3 | White-green | CAN1_H (control plus low-rate telemetry) | All |
| 4 | Pair 2 | Blue | STREAM_P (RS-485 data, module to Hub) | Pro+ |
| 5 | Pair 2 | White-blue | STREAM_N (RS-485 data, module to Hub) | Pro+ |
| 6 | Pair 3 | Green | CAN1_L | All |
| 7 | Pair 4 | White-brown | Reserved spare (no distributed reference; OQ-3 resolved) | All |
| 8 | Pair 4 | Brown | DETECT / module-ID (analog single-wire sense) | All |

- Pair 3 (pins 3 and 6) is the T568B split pair and stays twisted in the cable.
  Standard tier leaves pair 2 (pins 4 and 5) unused, terminated at the module
  side.
- DETECT (pin 8) is an analog single-wire identity and presence sense: a
  precision resistor from pin 8 to GND on each module, read by the Hub through a
  fixed 10 kΩ pull-up to its 3.3 V ADC reference (NOT the 5VSB VCC pin — a 5VSB
  pull-up would exceed the ESP32 ADC range) as a divider on an ADC channel. An
  open line reads near 3.3 V (no module); a short reads 0 V (fault). DETECT code
  table RESOLVED v1.7 (OQ-6), encoding LINK CAPABILITY (spec §2.3): CAN-only
  2.2 kΩ (0.595 V), CAN+RS-485 4.7 kΩ (1.055 V), CAN+100BASE-T1 10 kΩ (1.650 V),
  two reserved (22 kΩ / 47 kΩ). 24-pin/EPS/PCIe/12VHPWR-Std are CAN-only (2.2 kΩ);
  12VHPWR Pro is CAN+RS-485 (4.7 kΩ).

Communication:
- All control and command traffic lives entirely on CAN, on pair 3, for every
  tier. CAN carries control plus low-rate telemetry.
- Classical CAN at 500 kbps on EVERY tier, Standard through Mission Critical
  (CAN-FD DEFERRED platform-wide, spec §3.1 v2.0 — neither the ESP32-S3 nor the
  ESP32-P4 TWAI does FD in silicon, and one classical-only module on an FD bus
  forces the whole bus classical anyway). Transceiver: TJA1462A (CAN-FD-capable,
  run classical, leaves the door open). Termination: fixed 120 ohm split at Hub.
- Optional bus-wide 1 Mbps CAN (added v3.4): 500k stays the default and the
  floor; the whole shared bus may instead run classical CAN at 1 Mbps — never
  per-module (one TJA1462A, one CAN_H/CAN_L net, one split termination = one
  bitrate). Firmware-only: Hub-led auto-baud + TWAI error-counter fallback; the
  TJA1462A (SIC) and both TWAIs already do 1M and the Hub CAN front-end is
  unchanged. Sole gate: the §3.1 star/stub SI bench test, run at 1 Mbps. A
  DETECT-code bitrate advert was considered and declined (module-resistor cost,
  grows the locked DETECT table, no benefit — every module is already 1M-capable;
  the real variable is per-install SI, which DETECT can't sense).
- RS-485 carries high-bandwidth telemetry streaming only, one direction, module
  to Hub, on pair 2. It carries no control traffic. Present on Pro modules and
  Pro+ Hubs only. Standard does not populate it.

Per-tier hardware:
- Hub Standard: ESP32-S3-WROOM-1-N16R8 (16 MB flash + 8 MB PSRAM, PCB-antenna
  keepout honored for future Wi-Fi; the MINI-1 has no 16 MB SKU, so the
  aggregation Hub uses WROOM while modules stay on MINI-1), 4 ports, classical
  CAN, USB Full Speed. v1.1 decisions
  carry forward (LP5907 LDO, 4700 uF aluminum electrolytic hold-up — Panasonic
  EEVFK1C472M 16 V, corrected from "polymer" v1.9; 1 ohm 1 W inrush
  resistor, SS14 reverse-polarity Schottky, TPS3839K33 supervisor, 7x SK6812
  MINI-E LED chain, GPIO0 hidden service button, 4x M3 chassis-grounded
  mounting, 4-layer 1.6 mm ENIG matte-black PCB, identity by factory MAC plus
  database with no eFuse or secure element).
- Hub Pro: ESP32-P4, 8 ports, classical CAN plus RS-485 streaming receivers (one
  receiver per port as the working basis, pending OQ-5), USB High Speed.
  Bulk power on the dedicated 2-pin +5VSB power-in connector (OQ-1, spec §2.7).
  Otherwise follows the Hub Standard base.
- 12VHPWR Pro module: ESP32-P4, INA240A3 per-pin current-sense amps on per-pin
  shunts, LTC2358-18 8-channel simultaneous-sampling 18-bit SAR ADC, 47k/10k
  rail-voltage divider into one LTC2358 channel, about 900 kB/s streaming
  (roughly 50 kHz x 6 channels) over RS-485, classical CAN control.
- Standard modules (24-pin ATX, EPS 8-pin, PCIe 8-pin, 12VHPWR Standard):
  ESP32-S3-MINI-1; no CAN termination (Hub-only). Per-module sensing differs by
  connector (spec §6.1, §6.2):
  - 24-pin ATX: 4x INA228 (20-bit, 195 uV bus LSB, internal energy/charge
    accumulators), one per rail — 12V, 5V, 3V3, 5VSB. The INA228 is a pin- and
    footprint-compatible (VSSOP-10) drop-in for the INA238. IMPLEMENTED in the
    24-pin schematic.
  - EPS 8-pin: INA238 per cable (per-cable granularity), 2 cables populated.
    IMPLEMENTED.
  - PCIe 8-pin: INA238 per cable, 3 cables populated (spec upper bound).
    IMPLEMENTED.
  - 12VHPWR Standard: six INA240 per-pin current-sense amps into the ESP32-S3
    ADC (GPIO1..6), plus a 47k/10k rail-voltage divider into a 7th ADC channel
    (GPIO7). No I2C sensing bus. REF1/REF2 tied to GND (unidirectional forward
    sensing). Accuracy ~+/-1%, see OQ-8. IMPLEMENTED.
  - Acquisition (spec §6.10): the digital-sensor modules (24-pin, EPS, PCIe) run
    their INA228/INA238 in continuous-conversion mode with a per-sensor ~2 s ring
    buffer of 1 kHz averaged samples (pre-roll), and use the ALERT pin as the
    threshold detector / buffer-freeze trigger. (Firmware concern; the ALERT net
    is left available at the part in the schematic.)
  - Shunt values (spec §6.4, LOCKED; parts pending OQ-11): 24-pin 12V/5V/3V3 =
    2 mΩ, 24-pin 5VSB = 25 mΩ; EPS and PCIe per-cable = 0.5 mΩ; 12VHPWR per-pin =
    1 mΩ. IMPLEMENTED in the generator/boards. Low-TCR precision metal-element
    shunts, four-wire Kelvin sense (§6.8) — Kelvin geometry is a layout (GUI)
    task, not in the generated schematic.

LED current:
- SK6812 aggregate current must be capped in firmware (global brightness or
  current budget) so the worst case stays within the connector rating with
  margin. Seven SK6812 at full white draw on the order of 0.4A per board, and a
  Hub plus several full-white downstream modules can push aggregate draw toward
  2A. With bulk power on the Hub's dedicated 2-pin power-in (OQ-1 resolved), that
  draw no longer concentrates on a single RJ-45 VCC pin, but it is still capped
  in firmware (OQ-2).

Cross-tier behavior:
- A module never fails to function in any Hub. A Pro module in a Standard Hub
  runs CAN control and event telemetry normally; its streaming pair is connected
  at the jack but stays dark because the Standard Hub populates no RS-485
  receiver. This is the intended graceful-degrade behavior and is expected.

## Open questions (do NOT assume; flag or ask)

These are unresolved in the spec. Do not silently pick an answer. If a design
choice depends on one of these, surface it and ask, or implement it behind a
clearly labeled branch or variant.

- OQ-1 (RESOLVED, v1.3): Hub bulk power input. Locked to a dedicated 2-pin
  +5VSB power-in connector on every Hub, separate from the RJ-45 interface, fed
  from the 24-pin ATX module; the Hub distributes 5VSB to its ports over the
  RJ-45 VCC pin. See spec §2.7. This removes the single-pin trunk constraint.
- OQ-2: Total 5VSB current cap (broadened from an LED-only cap). Confirm the
  firmware cap on total CEC 5VSB draw (LED budget is the main lever) and the max
  LED state to budget for, sized within the JST-XH rating and the shared ~2.5A
  5VSB rail with margin. See spec §2.5.
- OQ-3 (RESOLVED, v1.1): Precision reference path. Local REF3033 on each Pro
  module; NO distributed reference; pin 7 is a reserved spare. See spec §3.3.
  (Do not treat pin 7 as AUX_REF anymore.)
- OQ-4: Cable length SKUs and whether Pro modules are allowed on arbitrary user
  cables. Interacts with OQ-3.
- OQ-5: RS-485 topology. One receiver per Hub port (point-to-point, working
  basis) versus a shared multidrop bus across ports.
- OQ-6 (RESOLVED, v1.7): Module-ID encoding. DETECT code table locked in spec
  §2.3 — pin 8 encodes LINK CAPABILITY on a 10 kΩ / 3.3 V divider (CAN-only
  2.2 kΩ, CAN+RS-485 4.7 kΩ, CAN+100BASE-T1 10 kΩ, two reserved, open = absent,
  short = fault). Module type and tier ride on CAN once the link is up.
- OQ-7: Whether to fully specify Enterprise and Mission Critical now or keep them
  at platform-summary level.
- OQ-8: 12VHPWR Standard rail accuracy. Sensing through the ESP32-S3 ADC (INA240
  + 47k/10k divider) caps accuracy near +/-1%. Accept that, or add a local
  REF3033 to that one board (improves to ~+/-0.3 to 0.5%, INL-limited).
- OQ-9: EPS/PCIe transient capture. The INA238 averages out ms transients;
  decide whether bundled EPS/PCIe need an INA240-style fast path or averaged
  total power suffices.
- OQ-10: Bundled-shunt vertical transition (copper coin vs filled-via field vs
  plated slot) for the ~40 to 55A EPS/PCIe per-cable shunt sites. See §6.7.
- OQ-11: Per-module shunt part selection (value, TCR, tolerance, package, power)
  per the §6.4 shunt table.
- OQ-12: Per-module high-current stackup (L3-rails-with-via-detour vs top-layer-
  rails) per high-current module. See §6.7.
- OQ-13: Energy reporting scope. 24-pin INA228 gives hardware energy/charge on
  all four rails; decide whether energy is scoped to that 24-pin/standby figure
  or extended to total system energy (firmware integration on EPS/PCIe/Pro). The
  24-pin energy is partial and must not be presented as total.
- OQ-14 (RESOLVED for consumer, v2.0): PoE/over-voltage protection. Standard and
  Pro carry NO per-pin PoE clamp (board state ratified, §2.4); a low-cap ESD diode
  on DETECT pin 8 is LOCKED separately on every Hub and module (Hub Standard has
  it — D2-D5; modules + 24-pin rev2 pending — action item). Enterprise/MC
  over-voltage moves to their external uplink (OQ-7).
- OQ-15 (spec): Max positioning — is the 12VHPWR Max a new platform tier or a
  module variant (§6.11)? [In the OLD repo numbering OQ-15 meant the shielded-jack
  divergence; that is now OQ-37.]
- Canonical OQ list is OQ-1..OQ-37 in spec §10 (it now also covers the Max §6.11,
  SATA §6.12, ARGB §7, and the compute/Enterprise questions). Read the spec for
  any OQ above 13 — do not assume from this summary.

## Active action items

Keep this section honest after every revision: when a board rev actually lands a
fix, move the item to Done with the board name + date; when a rev opens a new
gap, add it. The Done list and the per-board status notes above (e.g. the DETECT
ESD diode, the FTP jack) must reflect real, verified board state — not intent —
so a fresh reader can trust them without re-deriving from the schematic. Update
this file in the same change that touches the board, not later.

Open items (surface before acting):

1. DETECT pin-8 ESD diode (§2.4, LOCKED v2.0): platform-wide requirement.
   Hub Standard DONE (2026-06-04): D2-D5 = PESD5V0S1UL (SOD-323), one per port,
   cathode to each DETECT line, anode to GND (verified ERC/netlist).
   EPS/PCIe/12VHPWR-Std SCHEMATICS DONE (2026-06-04): D1 = PESD5V0S1UL on DETECT
   pin 8 (+ R7 100k poke-and-ack tap to IO10) via gen-modules.py, regenerated and
   verified (static audit + exported netlist). STILL PENDING: assign the D1
   footprint at layout on each; the ordered 24-pin rev2 PCB shipped without it
   (rev3 picks it up).
2. FTP shielded jack (§2.1 / OQ-37): Hub Standard schematic DONE (2026-06-04) —
   J2-J5 now assign cec:RJ45_FTP_Shielded_Horizontal (pad-identical to the 54602,
   routing-preserving). STILL PENDING: (a) MPN -> an LCSC shielded TH non-magnetic
   jack for JLC assembly; lead candidate CONNFLY DS1129-05-S80BP-X (LCSC C86580 —
   shielded copper shell, no LED, TH, 1.5A, in stock; alt Kinghelm KH-RJ45-58-8P8C
   / C2683360). Pull the part's authoritative EasyEDA footprint via
   `easyeda2kicad --full --lcsc_id=C86580`, commit the .kicad_mod into lib/, and
   repoint J2-J5 at it (replaces the generic cec:RJ45_FTP_Shielded_Horizontal;
   guarantees JLC pick-and-place alignment). NOTE: the environment network policy
   was updated 2026-06-04 to allow LCSC/EasyEDA for FUTURE sessions; that change
   does NOT apply to an already-running session, so it must be picked up in a
   fresh session (until then the import 403s; only PyPI/GitHub are reachable).
   NEXT-SESSION TODO: run that import first thing, or paste the datasheet PCB
   layout to build it in-repo; (b) in the GUI run "Update PCB from Schematic" to pull the footprint
   onto the placed J2-J5; (c) modules + 24-pin rev2 still carry the unshielded
   54602 (compatible — single-end shield at the Hub) — move them to FTP on their
   next rev.

Done (kept for context):
- Mini-Fit Jr -> RJ-45 re-cut COMPLETE on every board's module-to-Hub interface
  (after any future edit, verify no Mini-Fit Jr is used for the module-to-Hub
  link or Hub bulk power, and the eight RJ-45 pins match the pin allocation
  table). EXCEPTION: the 24-pin ATX module's PSU-side power path (J3/J4) is
  Mini-Fit Jr by design (ATX standard, §2.8) — that is correct, not a leftover.
- 24-pin INA238 -> INA228 swap IMPLEMENTED; KiCad-10 library modernization and
  the cec-power nickname are in.
- EPS/PCIe per-cable sensing (EPS x2, PCIe x3) and the 12VHPWR Standard 6x INA240
  per-pin redesign IMPLEMENTED in gen-modules.py (INA240 symbol vendored).
  Regenerated + completed 2026-06-04: decoupling brought up to the 24-pin gold
  standard (2x 10uF bulk + 1uF LP5907 in/out + per-IC 100nF, incl. dedicated
  TJA1462A VCC/VIO bypass); DETECT R1 set to the resolved CAN-only 2.2k code
  (OQ-6); ESP corrected to a real MINI-1 SKU (N4R2 — N16R2 was fictitious);
  D1/R7 picked up; and the per-cable IN/OUT interposer pitch widened to 100 mm so
  adjacent cables no longer merge SENSE nets. EPS verified: static audit clean,
  ERC clean apart from the by-design GPIO0 isolated-label and the known generator
  lib_symbol_mismatch noise (ERC is skipped for DRAFT boards anyway).
- §6.4 shunt values applied across the generator/boards.
- Still firmware/layout work (not schematic): the §6.10 acquisition model and the
  §6.8 Kelvin shunt geometry.

## KiCad environment

- Target KiCad 10 (current stable in the 10.0.x series). Do not save project
  files with an older major version; the file format is forward-only and a board
  saved in 10 will not open in 9. Keep the local install and any CI or container
  on the same major version.
- `kicad-cli` ships with KiCad and runs headless. It must be on PATH wherever
  Claude Code runs. For CI or a container, use the official KiCad kicad-cli Docker
  image rather than a full GUI install.
- Library paths are project-relative via `${KIPRJMOD}`.
- Pinned toolchain version lives in `versions.env` (KiCad major pinned to 10, the
  10.0.x series); the scripts and CI read it. The `.kicad_*` format is
  forward-only.
- The repo is self-contained for clone parity: official and third-party parts are
  vendored into `lib/vendor/`, their 3D models into `lib/3dmodels/`, all
  referenced by `${KIPRJMOD}`-relative paths — no machine-global libraries.
  `scripts/vendor-libs.sh` brings parts in at the pinned library tag. Never
  reference `${KICAD*_3DMODEL_DIR}` or absolute paths.
- Library-table NICKNAMES must be namespaced `cec` / `cec-*` (e.g. the vendored
  `Package_SO.pretty` is registered as `cec-Package_SO`, not `Package_SO`). A bare
  stock nickname collides with the same-named machine-global KiCad library, which
  on another PC can shadow the in-repo copy and break footprint lookup (this bit
  us once: an old global `Package_SO` lacking `VSSOP-10_3x3mm_P0.5mm` shadowed the
  vendored one, so the INA228 footprints "could not be found"). The `.pretty`/
  `.kicad_sym` FOLDER names stay stock; only the table nickname is prefixed.
  `scripts/vendor-libs.sh verify` enforces this (fails on any non-`cec` nickname).

## Commands to use

Run from a board directory and substitute the board file name. ERC and DRC
return exit code 0 on a clean run and 5 when violations exist, and emit JSON for
parsing.

```bash
# Electrical rule check (schematic)
kicad-cli sch erc --exit-code-violations --format json -o erc.json BOARD.kicad_sch

# Design rule check (layout)
kicad-cli pcb drc --exit-code-violations --format json -o drc.json BOARD.kicad_pcb

# Netlist: verify connectivity against the locked pin allocation table
kicad-cli sch export netlist -o BOARD.net BOARD.kicad_sch

# BOM: cross-check against the per-board target and the spec BOM summary
kicad-cli sch export bom -o BOARD-bom.csv BOARD.kicad_sch

# Visual check: an image to inspect silk and placement
kicad-cli pcb render -o BOARD-top.png BOARD.kicad_pcb

# Fab outputs (generate into the gitignored /build/ working dir)
kicad-cli pcb export gerbers -o ../../build/BOARD/gerbers/ BOARD.kicad_pcb
kicad-cli pcb export drill   -o ../../build/BOARD/gerbers/ BOARD.kicad_pcb
kicad-cli pcb export pos     -o ../../build/BOARD/BOARD-pos.csv BOARD.kicad_pcb
```

If a `.kicad_jobset` is defined for a board, prefer regenerating all fab outputs
with `kicad-cli jobset run` so settings match the GUI. Confirm exact flags with
`kicad-cli jobset run -h`.

## What Claude should do

- Run ERC and DRC, parse the JSON, and report exactly which nets, footprints, or
  clearances are at fault.
- Verify connectivity from the exported netlist against the locked pin
  allocation table (for example, confirm pin 8 lands on the DETECT resistor
  divider, and confirm pins 4 and 5 carry the RS-485 pair only on Pro+ boards).
- Cross-check the exported BOM against the per-board target and the spec BOM
  summary, and flag drift.
- Author and maintain design rules (`.kicad_dru`) and netclasses. Define a power
  netclass with a minimum trace width sized for the 5VSB trunk worst case: the
  dedicated 2-pin power-in and the Hub's internal 5VSB distribution carry the full
  trunk (toward 2A on the 8-port Pro), while each RJ-45 VCC pin carries only one
  module's draw. DRC then flags any power trace that is too thin. (Final width
  still depends on the OQ-2 LED cap.)
- Place and arrange footprints in `.kicad_pcb`: set or adjust a component's
  position and rotation (its `(at X Y A)` line), size the board outline
  (Edge.Cuts), and add mechanical or decorative elements (mounting holes tied to
  GND, branding/logo footprints, the SK6812 LED ring). This is floorplanning, not
  routing — placing parts and orienting connectors is fine; pulling traces is
  not. After ANY placement edit, verify before reporting done:
  - **Render and DRC.** Run `kicad-cli pcb render` to confirm orientation
    (connector mouths and the ESP32-WROOM PCB antenna face the intended board
    edge) and DRC for courtyard overlaps, copper-to-edge, and clearance. Separate
    the real hits from cosmetic/pre-existing noise (0.2 mm legacy drills, a
    footprint's own silk-over-pad, benign lib-footprint-mismatch).
  - **Everything in the footprint is LOCAL — move it by the one anchor.** Pads,
    silk/fab graphics, the Reference/Value and any user text, and any
    footprint-local zones or keep-outs are all stored relative to the footprint
    origin, so editing the single `(at X Y A)` line carries the whole part along
    — text and zones included. Never relocate a footprint by hand-moving its
    children one at a time; that orphans the text or a keep-out off the part.
    After the move, glance at a render to confirm nothing detached. The per-pad
    angle field is baked (footprint angle + local), so when you change a
    footprint's rotation, normalize its pad angle fields to match, or the
    instance is left internally inconsistent.
  - **Rotate, don't flip.** Changing the angle `A` rotates the part in place
    (normalize the pad angles as above) — fine, and account for any rotation the
    footprint already carries. Do NOT flip a footprint to the other side of the
    board by hand: a flip is a layer change (the footprint and every child move
    `F.*` → `B.*` and X mirrors), i.e. an opposite-side placement decision, not a
    coordinate edit. Leave flips to the GUI or do them only on explicit
    instruction.
  - **kicad-cli cannot refill zones.** Moving a footprint under a filled pour
    leaves stale fill that DRC reads as a false short; clear the stale
    `(filled_polygon)` blocks (or leave the zone unfilled) and tell the user to
    re-fill with `B` in the GUI.
  - **Known kicad-cli artifact:** rotating a footprint's text can yield FALSE
    within-footprint pad-short / mask-bridge DRC hits headlessly (seen on the
    SK6812 LEDs). Cross-check a render before believing them — they do not appear
    in the GUI.
- Maintain the shared library and the vendored libraries (`lib/vendor/`,
  `lib/3dmodels/`), the library tables (project-relative), CI, jobsets, and
  documentation, and keep this file in sync with the spec AND with verified
  board state after every revision (see "Active action items").
- Confirm universal-interface parts are sourced from `lib/` rather than
  duplicated per board.

## What Claude should NOT do

- Do not hand-edit PCB ROUTING geometry — track segments, vias, and the copper
  zone fill — in `.kicad_pcb`. Routing and the final pour are done interactively
  in the KiCad GUI; that is the boundary that stays in the GUI. Likewise leave
  fine layout geometry (e.g. the §6.8 four-wire Kelvin shunt sense) to the GUI.
  Component PLACEMENT is allowed and expected — see "What Claude should do".
- Editing `.kicad_sch` IS allowed: drafting and tidying a schematic, especially
  library-driven, is reasonable. Treat it as real work, though — wire-to-pin
  connections and junctions are where edited or generated schematics break, so
  after any schematic edit verify with ERC and the exported netlist that every
  pin is connected and there are no stray or overlapping junctions.
- Do not resolve any open question (OQ-1 through OQ-7) by assumption. Surface it
  and ask.
- Do not change a locked decision. If a change seems warranted, propose a spec
  revision first; the spec is ground truth.
- Do not commit generated outputs to `main` as routine churn. Snapshot fab
  outputs under `fab/<rev>/` only at a tagged release.

## Project-specific verification checklist

Use this as a recurring review pass:
- All module-to-Hub connectors are RJ-45 8P8C and no Mini-Fit Jr is used for the
  module-to-Hub link or Hub bulk power. (The 24-pin ATX module's PSU-side power
  path J3/J4 ARE Molex Mini-Fit Jr by design — §2.8 — and the 12VHPWR module's
  12V-2x6 connector is soldered to the board; neither is a violation.)
- Pinout on every board matches the locked pin allocation table (pin 7 is a
  reserved spare, NOT AUX_REF).
- PoE/over-voltage protection (RESOLVED for consumer, §2.4 v2.0): Standard/Pro
  carry NO per-pin PoE clamp (ratified). Instead verify a low-cap ESD diode is
  present on each DETECT pin-8 line (LOCKED v2.0) — Hub Standard has it (D2-D5,
  PESD5V0S1UL); the modules + 24-pin rev2 still lack it, so flag that absence.
- RJ-45 shielding (§2.1 / OQ-37): spec LOCKS FTP. Hub Standard now assigns the FTP
  footprint (cec:RJ45_FTP_Shielded_Horizontal) on J2-J5; before fab verify the
  chosen shielded MPN's SH1/SH2 + peg geometry matches that footprint. Modules +
  24-pin rev2 still carry the unshielded 54602 (compatible — single-end shield at
  the Hub, link is shielding-insensitive).
- DETECT (pin 8) resistor matches the §2.3 code table: CAN-only modules = 2.2 kΩ
  (24-pin/EPS/PCIe/12VHPWR-Std), 12VHPWR Pro = 4.7 kΩ; read on the Hub's
  10 kΩ / 3.3 V divider.
- Module sensing matches §6.1: 24-pin = 4x INA228; EPS = per-cable INA238 (1-2);
  PCIe = per-cable INA238 (up to 3); 12VHPWR Standard = 6x INA240 per-pin +
  divider; 12VHPWR Pro = INA240 + LTC2358-18. (EPS/PCIe/12VHPWR-Std schematics
  reconciled + regenerated 2026-06-04; PCB layout still pending.)
- Shunt values match the §6.4 table (24-pin 2 mΩ / 5VSB 25 mΩ; EPS/PCIe 0.5 mΩ;
  12VHPWR 1 mΩ), Kelvin-sensed.
- RS-485 pair (pins 4 and 5) and its receivers exist only on Pro and above;
  Standard leaves pair 2 unused and terminated at the module side.
- CAN termination is a fixed 120 ohm split at the Hub.
- Power netclass trace width covers the trunk worst case (the dedicated 2-pin
  power-in and Hub 5VSB distribution carry the trunk; RJ-45 VCC is per-port); the
  firmware LED current cap is reflected in the design intent.
- Libraries and 3D models are vendored in-repo and referenced by
  `${KIPRJMOD}`-relative paths only — no machine-global or absolute paths.
- BOM totals are in line with the spec targets.
