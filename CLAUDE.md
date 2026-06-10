# CLAUDE.md

Operating guidance for Claude Code working in the CEC platform repository.

## Ground truth and precedence

`CEC-Platform-Ground-Truth-Spec.md` is the canonical specification and holds
precedence over everything else, including this file. Where this file and the
spec disagree, the spec wins, and this file should be updated to match. Treat
this file as a working summary plus operating instructions, and read the spec
before making any design decision.

Spec revision reflected here: **v1.1.0 (2026-06-09), controlled baseline** (semantic
versioning; supersedes the pre-release v1.0–v3.11 working line, whose detailed log is
retained for provenance in spec §11.1). The canonical-spec-line question (the old repo
v3.x file vs the controlled release) is now RESOLVED: the v1.1.0 controlled baseline is
canonical (owner direction, 2026-06-09), installed as `CEC-Platform-Ground-Truth-Spec.md`.
The pre-release (vX.Y) tags below remain valid as references into spec §11.1.

What v1.1.0 adds over the v3.10 summary below (no hardware change, no LOCKED decision
altered): (a) document control + semantic versioning + a TOC/index; (b) **Appendix D —
the support pipeline** (PROPOSED throughout, gating decisions OQ-61..OQ-74): the eight-stage
closed loop (request → collect diagnostics → swarm candidate-plan generation with sandbox
validation on config-replica VMs holding no user data → judge routing/scoring → signed-plan
execution behind a verified restore point + rendered consent → verification with a monitored
horizon → human/verifier sign-off emitting an outcome label → de-identified corpus write).
Appendix D is the **actuation half** of the loop whose sensing half the platform already
builds, it is the conceptual backbone the agentic-pipeline addendum
(`docs/self-building-pipeline-addendum-2026-06-09.md`) and the punchlist
(`docs/agentic-pipeline-review-2026-06-09.md`) operate against, and its design rules
(agent neutrality = no generative model on the customer machine; evidence-over-local-
intelligence; gates at zone crossings) mirror the §1 processing-placement principle. The
OQ range grew to **OQ-1..OQ-74** (Appendix D opened OQ-61..74; v3.11 opened OQ-60). Companion
diagrams `cec-subsystem-power-management.svg` (§2.9) and `cec_closed_loop_support_pipeline.svg`
(Appendix D) are referenced but NOT vendored in the repo; both have inline text renderings in
the spec, so the absence is non-blocking (track as a docs follow-up).

v3.10 (2026-06-05) — SPEC CONSOLIDATION (merged the canonical v3.9 upload's revised
architecture into this board-reconciled line; both forked from the shared v3.7 base).
ADOPTED: (1) the three digital-sensor Standard modules (24-pin, EPS, PCIe) move
ESP32-S3-MINI-1 -> **ESP32-C6-MINI-1** (C3-MINI-compatible footprint; 24-pin + EPS can
cost-down to **C3-MINI** once their NTC count is fixed). 12VHPWR Standard KEEPS the
S3-MINI-1 (9 analog ins + N4R2 PSRAM); Hub KEEPS the S3-WROOM-1-N16R8. (2) **§6.13
EPS/PCIe transient-visibility ladder**, resolving OQ-9: Standard EPS/PCIe gain a cheap
analog DETECTION front-end on the shunt (INA181-class CSA + hysteresis comparator ->
firmware-settable threshold -> ORs into the §6.10 FREEZE trigger, ~$0.85/cable) that
flags a transient as a BINARY event (sees that it happened + the averaged envelope, NOT
the sub-ms waveform); magnitude/shape are held to NEW EPS Pro/PCIe Pro (INA240 + fast
ADC + RS-485) and EPS Max/PCIe Max (per-cable spectral, no per-pin arc) SKUs. (3) v3.8
doc fixes (§2.8 12V-2x6 sideband pass-through, §2.9 S5 5VSB tap downstream of the 24-pin
sensor, §6.6 chassis thermal coupling / TIM under the EPS/PCIe shunts) + OQ-57..59.
PRESERVED from this line (the upload fork predated both): REF3030 (12VHPWR Standard,
OQ-8 middle ground) and the S5B right-angle NanoKVM connector (OQ-51). OQ list is now
**OQ-1..OQ-59**. BOARD DIVERGENCE OPENED — the spec now LEADS the boards: the C6/C3 MCU
change and the §6.13 detection front-end are NOT yet on the as-built 24-pin/EPS/PCIe
schematics (all on ESP32-S3-MINI-1; EPS was just sourced on S3-MINI-1-N4R2 C3013941 with
no detection front-end). See the action item below.

v3.9 (2026-06-05, right-angle aux connector): J7 (NanoKVM aux) is the RIGHT-ANGLE
S5B-PH-K-S (LCSC C157923, footprint cec-Connector_JST:JST_PH_S5B-PH-K-S_1x05_P2.00mm_
Horizontal), NOT the top-entry B5B-PH-K-S — revises the v3.7 OQ-51 connector form. Same
JST PH family / 2.0mm / 5-circuit / keyed / 2A and the IDENTICAL 1x5 @ 2.0mm THT hole
pattern (drop-in on the same lands); only the entry direction changes: side-entry, so the
external NanoKVM cable runs PARALLEL to the board and exits a board edge (top-entry B5B
needed vertical headroom a cased Hub does not want). Per the user's direction. J7 schematic
repointed (pinout/value unchanged), ERC clean, J7 netlist unchanged. Footprint via
easyeda2kicad C157923 + kicad-cli fp upgrade to KiCad-10; 3D vendored
lib/3dmodels/Connector_JST.3dshapes/S5B-PH-K-S.step. The B5B-PH-K-S vertical footprint
stays in the lib (harmless; unreferenced).

v3.8 (2026-06-05, REF3030 ratiometric ref): the 12VHPWR Standard gains U4 =
REF3030 (3.0V, SOT-23, cec-vendor:REF3030, MPN REF3030AIDBZR) + 2 bypass caps,
measured on ESP ADC1 IO8 for ratiometric correction — firmware ratios out the ESP-
ADC gain/ref drift, lifting the rail divider + all 6 INA240 currents from ~±1% to
~±0.3-0.5% (R5/R6 now 0.1%). IO8 freed by moving the SENSE0 sideband tap IO8->IO15
(digital, ADC2). Spliced into the routed schematic (ERC clean apart from benign
lib_symbol_mismatch; netlist-verified VREF=REF.OUT+IO8+bypass, SENSE0=R10+IO15;
UUIDs preserved). REVISES the v3.7 OQ-8 no-ref call — the middle ground below the
Pro's LTC2358-18. NOTE the part: Standard REF3030=3.0V is MEASURED by the ADC (must
sit in the ADC range); the Pro's REF3033=3.3V feeds the LTC2358 ref (different use).
New cec-vendor:REF3030 symbol + UltraLibrarian DBZ3 footprint (cec-Package_TO_SOT_SMD:REF3030_DBZ3); pinout SOT-23 DBZ 1=IN/2=OUT/3=GND -- the user-supplied UL files CORRECTED an earlier hand-made 1/3 (IN/GND) swap that would have reversed the reference supply (re-verified: U4.1 IN->+3V3, U4.2 OUT->VREF, U4.3 GND->GND). LCSC C38423 (in LCSC stock, ~$0.14).

v3.7 (2026-06-05): RESOLVED the NanoKVM aux-link FORM (OQ-51). The link is a
reserved keyed **5-pin JST-PH** aux header (vendored B5B-PH-K-S — now the right-angle
S5B-PH-K-S per the v3.9 correction above) on every Hub,
carrying the full set of pins the NanoKVM brings out on its own header: the
full-duplex 3.3V UART (TX/RX), the SHARED 5V feed + ground (§2.9), and the
NanoKVM's 3.3V reference/presence line. NO trigger GPIO — the NanoKVM exposes no
drivable interrupt input (framebuffer-capture latency caps a fast trigger anyway),
so event triggers ride the UART in-band; this is what "simplifies the header."
Baud (921600 working) + framed protocol stay firmware-open. NOTE: this corrects a
momentary mis-read that the NanoKVM exposed ONLY UART/GND/3V3 — it DOES also expose
5V + GND, so the §2.9 shared rail and the wall-wart-through-NanoKVM forensic path
are confirmed and STAND (an interim UART-only v3.7 draft was reverted first). Header
pin set for the J7 splice below: TX, RX, SHARED_5V (=+5VSB rail), GND, KVM_3V3_REF.

v3.7 (2026-06-05, 12VHPWR temperature add): the 12VHPWR Standard module gains two
NTC thermistor dividers (real part Murata NCP15XH103F03RC / C77131; TH1 by the
shunt row = board/shunt temp, TH2 ambient) into spare ESP32-S3 ADC2 IO13/IO14, reporting temperature +
dT-above-ambient — the INA240 has no die-temp sensor (unlike the 24-pin INA228),
so this is the module's only temperature source + the Appendix C.2 datum. Per
user (board-only): the NTCs are for measurement quality + board health —
shunt-TCR / INA-gain drift compensation of the per-pin current + 12V-section
overheat; the off-board GPU side is INFERRED by fusing temp + current + voltage,
and a pigtail/GPU-plug NTC (direct GPU-contact read) was DEFERRED. Spliced
into the routed schematic (ERC clean, netlist-verified TEMP1->IO13 / TEMP2->IO14;
all existing UUIDs preserved). OQ-8 RESOLVED (no local REF3033 on Standard:
transient-capture tier, not precision); 12V input TVS + status LED DECLINED. See
the 12VHPWR action item below and spec Section 6.1.

v3.6 consolidation (2026-06-05): merged the user's canonical v3.4 upload (the
subsystem-power / NanoKVM / Concierge architecture branch) into the board-
reconciled line. NEW: (1) **§2.9 Subsystem power management (PROPOSED)** — the
"power switching": the monitoring subsystem (Hub + NanoKVM, optionally the module
fleet) draws from THREE 5V sources via a hardware priority ideal-diode OR — PSU
main 5V (tapped after the 24-pin 5V sensor), 5VSB, and a wall-wart through the
NanoKVM USB-C — feeding one shared rail; firmware reads a rail-sense and sets the
load budget/mode (never switches its own supply → would deadlock the MCU). This
EXTENDS the as-built TPS2121 PSU/USB front-end mux (§2.7) from 2 inputs to 3
(same TI PowerPath family the OQ-55 part search names). Adds a forensic-recovery
path (wall-wart powers Hub+NanoKVM so flash data egresses over the NanoKVM
without opening the case) + persist-on-fault flush to the Hub's 16 MB flash. ALL
PROPOSED — parts (source-OR IC, back-feed isolation) + module-rail scope are
OQ-53..56; do not treat as locked. (2) Appendix C **Concierge** data-collection
(host/service layer; three-vantage fusion: electrical, OS-logical, NanoKVM
out-of-band visual). (3) **NanoKVM aux-link** row on the Hub tables (3.3V UART +
shared 5V feed). The upload's stale board facts (TJA1462A, MINI-1-N16R2,
1Ω-inrush/SS14 front end, polymer cap, M2.5) were OVERRIDDEN by this line's
as-built decisions, not imported. OQ list is now **OQ-1..OQ-59** (the upload's
OQ-37..55 were renumbered to OQ-38..56 to keep this line's OQ-37 = shielded jack).

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
    pcie-8pin-2port/           # PCIe SKU: 2 ports (4 connectors)
    pcie-8pin-3port/           # PCIe SKU: 3 ports (6 connectors)
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
| PCIe 8-pin 2-port | modules/pcie-8pin-2port | Standard | ESP32-S3-MINI-1 | - | - | $38 |
| PCIe 8-pin 3-port | modules/pcie-8pin-3port | Standard | ESP32-S3-MINI-1 | - | - | ~$42 |
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
  (FTP) jacks platform-wide. Hub Standard J2-J5 use cec:RJ45_FTP_Shielded_Horizontal,
  which (2026-06-05) is now the AUTHORITATIVE Kinghelm KH-RJ45-58-8P8C (LCSC
  C2683360) footprint pulled via easyeda2kicad and origin-aligned to the legacy
  1.27mm land (pad1..8 at (0,0)..(8.89,-2.54), so the 8 contacts stay routed; shell
  ground tabs renamed 9/10 -> SH1/SH2). MPN LOCKED (single shielded 8P8C, metal
  shell, right-angle TH, 1.5A). The prior C86580 candidate was rejected — it is a
  DUAL-port jack (wrong). The spec design-reference Wuerth 615008137421 (C132217)
  was declined: its real 1.02mm contact pitch does not match the board's 1.27mm
  routing (full re-route) and stock is thin (~166). REMAINING (GUI): "Update
  Footprints from Library" to pull the geometry onto J2-J5 — contacts preserved,
  reconnect the 2 GND shield tabs per jack. FTP migration (2026-06-06): Hub, 12VHPWR
  Standard AND **EPS** now carry the platform FTP jack (cec:RJ45_FTP_Shielded_Horizontal,
  Kinghelm KH-RJ45-58-8P8C / C2683360) with SH1/SH2 -> GND (both-end shielding+grounding,
  per the user). gen-modules.py now EMITS the FTP footprint + SH1/SH2->GND, so the
  **24-pin + the two PCIe SKUs pick it up on their next regen** (they still carry the
  UNSHIELDED 54602 / C2847314 until then — COMPATIBLE, not a conflict: an unshielded
  module jack terminates the cable shield at the Hub end only, the preferred single-end
  grounding, and the link is shielding-insensitive anyway: CAN + 5VSB + DETECT +
  Standard-dark RS-485).
- PoE/over-voltage protection (RESOLVED for consumer, spec §2.4 v2.0): Standard
  and Pro carry NO per-pin PoE-grade over-voltage protection on the RJ-45 module
  interface — the board state is RATIFIED (internal interface; 57V PoE injection
  is deliberate misuse; the realistic non-PoE network-jack accident is covered by
  the TJA1051T/3's own CAN bus-pin protection). This closes the consumer half of
  OQ-14. SEPARATELY LOCKED (v2.0): one low-capacitance ESD diode on the DETECT pin
  (pin 8 -> ESP32 ADC) on EVERY Hub and module, for hot-plug insertion ESD on the
  bare analog input. Hub Standard now populates this pin-8 ESD diode — D2-D5,
  PESD5V0S1BA in SOD-323, one per port, cathode to each DETECT line and anode to
  GND (added 2026-06-04, verified ERC/netlist; part corrected from PESD5V0S1UL to
  the SOD-323 sibling PESD5V0S1BA on 2026-06-05 — the UL is only stocked in
  DFN1006/SOD-882 by LCSC, the BA is the SOD-323 part the boards are laid out for,
  same low-cap single-line 5 V clamp; LCSC C5261083). The SAME UL->BA correction
  applies to the generated module schematics (EPS/PCIe), which still
  name PESD5V0S1UL "in SOD-323" — flag and fix on their next sourcing pass
  (12VHPWR-Std DONE 2026-06-06: D1 Value->PESD5V0S1BA + LCSC C5261083 on its full
  BOM-sourcing pass). D1 =
  PESD5V0S1UL via the generator, regenerated 2026-06-04 (footprint assigned at
  layout); the ordered 24-pin rev2 PCB still ships without it (rev3 picks it up). Enterprise/MC
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
  mated-contact pair from the power path. REALIZED FORM (2026-06-04, connector
  research): the 12V-2x6 (Molex Micro-Fit+ / Amphenol Minitek) is stocked only as
  a board-mount MALE header + a cable-crimp female — there is NO stock board-mount
  female. So the inline module is board-mount right-angle MALE header IN (PSU
  cable plugs in) + a captive soldered OUTPUT pigtail to the GPU (a 12V-2x6 cable
  soldered to the board, no detachable bridging cable) — the minimal-mated-pair
  form. Footprint cec:CEC_12V2x6_Horizontal is now the OFFICIAL Molex footprint
  (LOCKED 2026-06-05): Molex 219116 / PCIe CEM5 12V-2x6 right-angle THT header,
  MPN 2191161161 (T&R) = 2191160161 (tray), doc 2191160001-SD. Vendored from
  Molex's KiCad export with pads remapped to the CEC schematic numbering: pins 1-6
  = +12V (the row ADJACENT to the signal pins), 7-12 = GND (the OUTER row), 13-16 =
  sideband S1..S4. Real geometry: 3.0mm pin pitch / 3.0mm row pitch, power drill
  1.067mm (1.52mm pad), signal drill 0.61mm (1.14mm pad), 9.2A/power pin, 12V.
  NOTE pad gaps are ~1.5mm (real part) vs the old approximate ~0.6mm, so the +12V
  lanes can now NECK between the GND barrels. SAFETY: the connector is symmetric
  (both rows "POWER"); +12V vs GND is a system/CEM assignment — VERIFY pins 7-12 =
  GND (i.e. 1-6 = +12V) against PCIe CEM5.1 / the target GPU before powering, since
  the schematic ties 7-12 to the GND plane (a swap shorts +12V to GND). The
  generator's placement_hpwr J3/J4 ROTATIONS are now stale for this footprint (its
  mouth is on +y, so mouth-out-the-edge needs J3 rot 180 / J4 rot 0, not 0/180) and
  its placement coords assume the old pad rows — do NOT regenerate the GUI-owned
  board; pick the footprint up in KiCad via "Update Footprints from Library".

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
  forces the whole bus classical anyway). Transceiver: TJA1051T/3 — classical
  high-speed CAN, VIO=3.3V, LCSC C38695. LOCKED to the classical part (spec §3.1
  v3.5, 2026-06-05): with FD deferred platform-wide the FD/SIC-capable TJA1462A
  no longer earns its place — TJA1051T/3 is cheaper (~$0.40 vs ~$1.02), far better
  stocked (~121k vs ~166), pin-compatible SO8, and covers the 500k floor. The one
  trade: TJA1051T/3 is NOT a SIC (ringing-suppression) part, so the optional 1 Mbps
  loses the transceiver-side ringing help (see below); the 500k floor is fine.
  Termination: fixed 120 ohm split at Hub. STATUS (2026-06-05, DONE): propagated
  to every board carrying the transceiver — Hub Standard U2 + all six generated
  module schematics (U2 value -> TJA1051T/3, LCSC C38695, ERC clean each) + the
  gen-modules.py default. Hub Pro and 12VHPWR Pro have no transceiver placed yet,
  so they inherit the lock when built out. The unused cec-vendor:TJA1462AT symbol
  is left in the lib (harmless; not referenced by any board).
- Optional bus-wide 1 Mbps CAN (added v3.4): 500k stays the default and the
  floor; the whole shared bus may instead run classical CAN at 1 Mbps — never
  per-module (one TJA1051T/3, one CAN_H/CAN_L net, one split termination = one
  bitrate). Firmware-only: Hub-led auto-baud + TWAI error-counter fallback; both
  TWAIs and the TJA1051T/3 already do 1M and the Hub CAN front-end is unchanged.
  Sole gate: the §3.1 star/stub SI bench test, run at 1 Mbps — and with the plain
  (non-SIC) TJA1051T/3 there is NO transceiver ringing suppression, so that passive
  SI result is the whole story (a SIC part run classical is the fallback if 1M is
  needed and marginal). A
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
  EEVFK1C472M 16 V, corrected from "polymer" v1.9; TPS3839K33 supervisor, 7x
  SK6812 MINI-E LED chain, GPIO0 hidden service button, 4x M3 chassis-grounded
  mounting, 4-layer 1.6 mm ENIG matte-black PCB, identity by factory MAC plus
  database with no eFuse or secure element). Front-end reconciled to as-built
  (2026-06-04, spec §2.7): the TPS2121 PSU/USB priority mux does inrush limiting
  via its soft-start (C_SS 2.2 uF) and source-side reverse-current blocking, so
  the v1.1 discrete 1 ohm 1 W inrush resistor and a separate reverse-polarity
  diode are SUPERSEDED (this completes the v3.2 §2.7 fold-in, which the Hub
  table had not cleaned up). D1 is the downstream Schottky isolating the
  +5V_HOLD reservoir — BUILT as SB120 (1A/20V); the spec/README named SS14
  (40V), which is a drop-in higher-margin alternative (both fine on 5V).
  SK6812 data level shift (2026-06-05): the ESP32's 3.3 V GPIO is below the 5 V
  SK6812 V_IH (0.7*VDD ~= 3.5 V), so the LED data line is buffered up to 5 V by
  U6 (SN74AHCT1G08 single 2-input AND with both inputs tied = a non-inverting
  AHCT buffer; SOT-23-5, VCC=+5VSB, C14 100 nF) with R14 330 ohm series into
  DL1.DIN — chosen over a VDD-drop diode to avoid any LED dimming. (The original
  pick 74AHCT1G34 buffer is NOT stocked by LCSC/JLCPCB; the 1G08-as-buffer is the
  JLCPCB-available equivalent in the same SOT-23-5 land — both inputs on LED_DATA,
  pin4 Y -> R14.) Added to the hand-maintained .kicad_sch via cec_sch splice, ERC
  + netlist verified (chain U1.IO25->U6->R14->DL1.DIN); PCB still needs Update-
  from-Schematic + place/route of U6/R14/C14. NOTE: scripts/gen-hub-standard.py is
  STALE (pre-mux, pre-WROOM, pre-ESD, pre-shifter) and now GUARDED with a refusal-
  to-run — the live schematic is hand-maintained, do NOT regenerate it (it would
  revert the board and break the routed PCB).
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
    sensing). Accuracy ~+/-1%, see OQ-8. IMPLEMENTED. v3.4 additions: (a) a
    per-channel INA240 input anti-alias/transient RC filter — matched 10 ohm
    series Rf on each input (RFH/RFL1-6) + a 470 nF differential cap (CF1-6),
    fc = 1/(2*pi*2*Rf*Cdiff) ~= 16.9 kHz so the ~10 kHz GPU transients pass at
    ~-1.3 dB and HF rolls off ahead of the ADC; Rf held at 10 ohm + matched (TI's
    INA240 ceiling) for negligible gain/CMRR error. True simultaneous 7-channel
    bandwidth is then ADC-limited, not analog-limited (ESP32-S3 SAR ~83 kSps shared
    -> ~12 kSps/ch round-robin; full 10 kHz Nyquist needs a reduced channel count or
    burst capture — firmware/OQ-8; the filter is sized so the analog path is not the
    bottleneck). (b) The four 12V-2x6 sideband sense pins (13-16: SENSE0, SENSE1,
    CARD_PWR_STABLE, CARD_CBL_PRES#) now pass through J3->J4 AND each taps a free
    ESP32-S3 GPIO (IO8/9/11/12) via a 1k series R (R10-R13), so firmware can read
    the cable's advertised power capability + present/stable state and report over
    CAN. The analog module's I2C pull-ups (R3/R4) moved into the i2c-only branch of
    gen-modules.py to free IO8/IO9 for two of those taps.
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
- Canonical OQ list is OQ-1..OQ-59 in spec §10 (v3.10): OQ-8 RESOLVED (REF3030 middle ground), OQ-9 RESOLVED (§6.13 transient ladder), OQ-57..59 opened (transient-ladder gating). OQ-1..37 as before (Max
  §6.11, SATA §6.12, ARGB §7, compute/Enterprise, OQ-37 shielded jack), plus the
  v3.6-imported OQ-38..56 (Concierge data-collection OQ-38..47, NanoKVM link
  OQ-48..52, and subsystem power §2.9 OQ-53..56). OQ-51 (NanoKVM link FORM) is
  RESOLVED v3.7 — 5-pin JST-PH aux header (UART TX/RX + shared 5V + GND + KVM 3V3
  ref), no trigger GPIO; baud/protocol still firmware-open. Read the spec for any
  OQ above 13 — do not assume from this summary.

## Active action items

Keep this section honest after every revision: when a board rev actually lands a
fix, move the item to Done with the board name + date; when a rev opens a new
gap, add it. The Done list and the per-board status notes above (e.g. the DETECT
ESD diode, the FTP jack) must reflect real, verified board state — not intent —
so a fresh reader can trust them without re-deriving from the schematic. Update
this file in the same change that touches the board, not later.

Open items (surface before acting):

-3. CLOSED-LOOP FRAMEWORK (2026-06-10, branch claude/closed-loop-wave1). The owner's refined
   pipeline model (docs/closed-loop-implementation-list.md, CL/AM/RB/DF/PC/FR/GR/CR items) is
   being implemented; **docs/closed-loop-parity-plan.md is the working plan of record** --
   read it BEFORE touching the corpus, judge tiers, orchestrator, or review machinery. Locked
   owner decisions (do not re-ask): corpus/ at root two-zone split; PRs-everywhere path-gated
   (CODEOWNERS + branch protection LIVE on main -- promoted/**, cec-policy.json, tests/golden/**
   need owner approval); all 263 entries migrated to staging (promoted/ empty pending owner
   re-sign); M2.7 license CLEARED (analyst binding); night venue = WSL2 + routing container;
   FR stays pinned 1.7.0 (baseline banked) until the FR-01 epoch event. Conflict resolutions
   (reality won): SB-13 status lifecycle kept (promoted = human_approved + signoff); class
   letters AS-BUILT (A=standard, B=spec-derived -- the CL-06 spec-first rule binds to B);
   CL-03 compiles to post-route copper synthesis + DRC, never router netclasses (FR ignores
   them, measured); CL-26 minimal night ALREADY RAN (2026-06-09). Landed: zones + SCHEMA.md +
   migrator + zone-aware lint + corpus-tree ledger hash + CODEOWNERS + branch protection.
   Landed wave-1 remainder (2026-06-10): CL-10 cec-policy.json (CODEOWNERS-gated) + scripts/cec_policy.py
   loader -- 3 load-time guards (load-bearing binding refused on license_cleared:false / failed-or-absent
   eval gate -- extractor/verifier/frontier/vision-judge are marked NON-load-bearing until their gates
   exist; DF-05/07 anti-ratchet firewall scan_banned() equality-on-token over the banned reward fields;
   clamp() bounds nightly allocations + ledger-logs every clamp -- the loop can never widen a bound);
   DF-01/06 + PC-01 in cec_ledger.py (decision() w/ claim+hook+settlement, settleable=claim&&hook =>
   capture:full else counter-eligible; settle()/label append-only DF-07; counter() AM-06 sidecar
   sharding; CLI decision/settle/label); CR-01/03 registry block in cec-policy.json (ratified:false
   pending Decision 21 -- owner sign-off). 25 new host tests green (tests/test_cec_policy.py +
   test_ledger_decision.py); cec_policy validate wired into checklist.sh. STILL OPEN wave-1: CL-02 owner
   half (machine account + RB-04 audit -- OWNER action). SB-08 golden re-run in-container post-change: PASS.
   Landed wave-2 start (2026-06-10, branch claude/closed-loop-wave2): CL-25 audit check pack + intake
   gate -- six classes as stable IDs (cec_constraints.CL25_CLASSES; NEW netclass-geometry-conformance
   [fires on the committed 12VHPWR lane vias -> CL-11 via golden unblocked; Kelvin-stub track exemption
   on shared force+sense nets], bom-field-lint [known-open OQ-11/THT gaps noted not failed],
   sch-pcb-sync [lib_symbols-excised ref-set diff]); intake_gate() (sch-side subset + severity-ERROR
   ERC, DRAFT-skip per repo convention) wired into cec_router.route() (named-reason refusal, ledger
   mode=intake, CEC_SKIP_INTAKE=1 override; CLI --intake); detect-resistor-code taught the Hub
   10k-pullup posture (was a false-fail on Hub Standard); synth DFM stage + netclass_geometry check.
   NOTE: the Hub "J7/D7/R19-R24 Update-from-Schematic pending" narrative in action item 0 is STALE --
   the sync checker measured the Hub ref sets IN SYNC (77 refs; sch newer than pcb, so a placement/
   route pass may remain, but the footprints exist on the PCB). In-container: 10/10 tests
   (tests/test_cl25_checks.py), EPS+Hub intake ADMIT, SB-08 golden PASS.
   ALSO landed (same session): CL-11 golden fixture seeding -- 4 frozen states in tests/golden/fixtures/
   (12vhpwr pre = committed lane-via board [240 /SENSEP* via-dim hits, band floor 100] / post = derived
   337-via normalize [zero via hits invariant, net-scoped via checker payload]; hub pre/post = git
   a271253~1/a271253 R15-R18 divider pair, pre carries the EXPECTED-FAIL marker until the TPS2121
   Class B entry lands -- runner fails the day it starts firing, forcing the flip per AM-02);
   scripts/cec_golden_fixtures.py (verify=CI gate, --freeze=derive); fixtures.json manifest;
   kicad-checks.yml step runs it in the pinned KiCad image (pcbnew); tests/holdout/ created
   (never-tune pool, grown from overrides/bench labels). Teeth verified (swapped fixture -> exit 1).
   Wave-2 remainder: CL-19 extractor eval, CL-03 full compiler, AM-04 FEM anchors; then waves 3-5.
   VLM for CL-22 -- BAKE-OFF RUN 2026-06-10 (docs/vlm-bakeoff-2026-06-10.md): all three local
   seats PASS the golden-render gate under the v2 facts-alongside protocol (12/12 gate verdicts;
   v1 naive protocol failed all three -- judge false-fired on the conformant board, Qwen3.6
   workers thinking-overran every grammar call -> they run nothink for judging). Registered in
   broker + compose: cec-vision-judge (Qwen3-VL-32B :8006), cec-worker-vision (:8012),
   cec-worker-quality-vision (:8014). Harness scripts/cec_vlm_bakeoff.py (assets/run/show/html;
   full per-call transcript). Measured: seats canNOT measure (selection-vs-references only, CL-21
   confirmed on our boards; geometry stays with the deterministic checkers); they excel at
   structure/text reading (judge found the SS2.9 sensing gap BLIND). The 4 CL-11 fixtures are now
   BURNED for prompt tuning (AM-02) -- future charter iteration validates on tests/holdout/.
   Seat binding stays owner-gated (cec-policy.json edit = the Decision-8/9 act).

-2. SYNTH-PIPELINE PLACER -- design-pass deferred (2026-06-07, per user). The auto-placer
   (scripts/cec_synth_pipeline.py, place_with_consent + macro-block auto_cluster + overhang +
   anneal) is a strong GENERAL designer -- DRC-clean at the gen-eps-condensed bar (96x37, courtyard
   0 / short 0), fully synthesized from the netlist + Stage-1 asks -- BUT it is DOMAIN-BLIND: it has
   NO model of the high-current paths, the shunts, or the requirement that the sense devices
   (INA238/INA181) sit hard against their shunt's inner edge (short Kelvin), nor the high-current
   pour corridor (J_IN->shunt->J_OUT) kept clear, nor thermal separation. The user's read: it can
   likely go SMALLER still, and adding these as HARD constraints is a LOT more work or an entire
   reconsideration of the placement approach. DECISION: put the design pass ASIDE; for any ACTUAL
   board use the OLD design (the existing gen-*-condensed boards + cec_pcb explicit placement, which
   are untouched and remain the source of truth). The placer code stays as committed WIP on
   claude/synth-pipeline. WHEN RESUMED, the design pass must add: (1) high-current corridor keepout +
   pour reservation; (2) sense-IC-adjacent-to-shunt as a hard constraint (Kelvin); (3) the rest of
   the considerations list (thermal sep, routing channels, diff-pair proximity, symmetry) as hard
   constraints/score terms; (4) the drop-keepout trimmed-courtyard materialize for the real area win
   (currently the placer respects the ESP keepout for DRC-honesty -> bigger than needed); (5) the
   huge runner sweep wired to synth.yml. The cascade/resolve/triage/route-swarm-bridge backbone is
   DONE and independent of the placer. NEXT pipeline work is the placer-INDEPENDENT stages (physics
   FEA, sign-off, build+freeze, the run_pipeline driver on an existing board).

-1. v3.10 SPEC-vs-BOARD divergence (digital modules). The consolidated spec moved the
   24-pin/EPS/PCIe to ESP32-C6-MINI-1 (C3-MINI cost-down option) and added the §6.13
   per-cable transient DETECTION front-end (INA181-class CSA + hysteresis comparator +
   firmware threshold). STATUS (2026-06-06):
   - EPS + PCIe-2port + PCIe-3port SCHEMATICS DONE — all three regenerated on
     ESP32-C6-MINI-1-N4 + the §6.13 front-end, sourced, BOMs generated. C6 pin map
     netlist-verified (CAN_TX/RX -> IO20/21 pads 26/27, USB D+/D- pads 18/17, I2C pads
     24/25, EN pad 8, BOOT/IO9 pad 23, DETECT_SENSE pad 12, +3V3 pad 3, THRESH_PWM/IO14
     pad 19); §6.13 chain netlist-verified per cable (shunt SENSE_HI -> INA181A2 gain-50
     -> TLV7011 comparator -> firmware THRESH (MCU PWM IO14 + R10 10k/C40 100n) ->
     per-cable DET -> MCU GPIO latch, ORs into FREEZE). ERC = benign noise only
     (lib_symbol_mismatch generator cache + easyeda Unspecified pin_to_pin + C6 NC pad +
     CAN TXD pin_not_driven). gen-modules.py now EMITS C6 + §6.13 (MODS excludes the
     hand-maintained 12VHPWR-Standard; a guard refuses analog-pin boards). New vendored
     parts: cec-vendor ESP32-C6-MINI-1-N4 (C5736265), INA181A2IDBVR (C2058784),
     TLV7011DBVR (C702117); footprint cec-RF_Module:ESP32-C6-MINI-1 (+3D); D1 PESD UL->BA.
   - REMAINING (these three): PCBs need Update-PCB-from-Schematic to pull the C6 land +
     the §6.13 parts (U20-22 INA181, U30-32 TLV7011, R10/C40, per-cable bypass), then
     re-place/route/pour. Still unsourced on each: the per-cable 0.5mOhm shunts (OQ-11)
     and the Mini-Fit Jr THT power headers.
   - 24-pin ATX still on ESP32-S3-MINI-1 with no §6.13 front-end — carry the same C6 +
     §6.13 pass onto it next. 12VHPWR Standard (S3) + Hub (S3-WROOM) are unchanged by design.

0. §2.9 Subsystem power management — Hub Standard prototype (PARTIAL, 2026-06-05).
   POWER-SWITCHING CORE DONE in the schematic (ERC 0 errors, netlist verified, BOM
   sourced): cascade adds U7 = 2nd TPS2121 (C485916, reuse U5's part) ORing
   MAIN_5V_RAW (priority) > PSU_5V (= U5's 5VSB/USB OR) -> +5VSB, giving the
   MAIN_5V > 5VSB > USB priority the spec wants without touching U5's inputs. Done
   via ONE wire cut (U5.OUT->rail) + relabel U5.OUT to PSU_5V; U7.OUT carries the
   +5VSB rail (D1/hold-up/LDO/loads unchanged). MAIN_5V feed = J8 (S2B-XH-A, reuse
   J1's part); two 47k/10k source-sense dividers -> ESP32 IO9 (MAIN_5V_SENSE) /
   IO10 (5VSB_SENSE) for the firmware budget/mode pick; PWR_FLAGs on MAIN_5V_RAW +
   PSU_5V (the TPS2121 OUT pin is typed power_in, so the intermediate needs one).
   FOLLOW-UPS: (a) J7 NanoKVM aux header — DONE in the schematic (2026-06-05; ERC
   clean apart from benign mismatch + the 2 pre-existing off-grid flags below, netlist
   verified, on-grid audit ok, BOM-sourced). 5-pin RIGHT-ANGLE JST-PH S5B-PH-K-S (J7, LCSC
   C157923; footprint JST_PH_S5B-PH-K-S_1x05_P2.00mm_Horizontal — changed from top-entry
   B5B-PH-K-S/C157993 per the v3.9 right-angle correction so the NanoKVM cable exits a board
   edge), FORM LOCKED v3.7 (OQ-51), symbol cec:CEC_NANOKVM_AUX_5P. Pins: 1 =
   +5VSB (shared §2.9 rail), 2 = GND, 3 = UART TX -> 33ohm R19 -> ESP IO11, 4 = UART
   RX -> 33ohm R20 -> ESP IO12, 5 = NanoKVM 3V3 ref. NO trigger GPIO (triggers ride
   the UART in-band). The 3V3 ref is sensed UNTRUSTED/RATIOMETRIC (the user's "can't
   trust the 3v3 beyond a shadow of a doubt" call): KVM 3V3 via 47k/10k (R21/R22) ->
   ADC1 IO1, AND the Hub's OWN +3V3 via an identical 47k/10k (R23/R24) -> ADC1 IO2;
   firmware takes the RATIO IO1/IO2 so the ADC + divider error cancel and a drifted/
   sagging KVM rail is detected, never used as a reference (the 10k legs also give a
   defined absent=0 presence). D7 (PESD5V0S1BA, C5261083) ESD-clamps the cabled ref
   pin. Same pass cleared the STALE §2.9 IO9/IO10 no_connects (they were wired to
   MAIN_5V_SENSE/5VSB_SENSE but still flagged no_connect -> no_connect_connected ERC,
   DRAFT-hidden). (The earlier IO13-as-presence idea was dropped for the IO1/IO2 ADC1
   ratiometric pair.) STILL OPEN: PCB (GUI) Update-from-Schematic to pull J7/D7/
   R19-R24, place + route, re-pour; and refresh the bom/ CSVs to add the 8 new lines.
   PRE-EXISTING (not from this work, left as-is): two off-grid endpoint_off_grid ERC
   on #FLG200/#FLG201 — the off-grid PWR_FLAG STAMPS that drive 5VSB_RAW / USB_VBUS
   (functional, just placed off-grid; gridsnap the flag+its coincident label together
   to clear), and the RJ-45 SHIELD-TAB no_connects (incl. the J5.SH2
   no_connect_connected) which are the pending GUI shield-grounding pass (action item
   2). (b) 24-pin module MAIN_5V tap (after its 5V INA228 shunt, so
   the draw counts in system 5V per OQ-13) -> feed the Hub's J8 ("24-pin next").
   (c) PRODUCTION: consolidate J1 (5VSB) + J8 (MAIN_5V) into one 3-pin feed (kept
   separate now so the existing 5VSB cable + Hub bench-test still work — "fix
   later"). (d) PCB (GUI): place U7/J8 near the front end, route the cut net
   U5.OUT->U7.IN2 and U7.OUT->the +5VSB/D1 node, route the IO9/IO10 taps, re-DRC.
   (e) OQ-56: bench-verify the 4700uF hold-up rides a flash write. The chosen part
   (cascade TPS2121, not the $7.77 LTC4417 triple-prioritizer) is the cost-right
   call for the $36 Hub; LTC4417 is the textbook part for a non-cost-constrained
   (Enterprise/MC) board.

1. DETECT pin-8 ESD diode (§2.4, LOCKED v2.0): platform-wide requirement.
   Hub Standard DONE (2026-06-04): D2-D5 = PESD5V0S1UL (SOD-323), one per port,
   cathode to each DETECT line, anode to GND (verified ERC/netlist).
   EPS/PCIe/12VHPWR-Std SCHEMATICS DONE (2026-06-04): D1 = PESD5V0S1UL on DETECT
   pin 8 (+ R7 100k poke-and-ack tap to IO10) via gen-modules.py, regenerated and
   verified (static audit + exported netlist). STILL PENDING: assign the D1
   footprint at layout on each; the ordered 24-pin rev2 PCB shipped without it
   (rev3 picks it up).
2. FTP shielded jack (§2.1 / OQ-37): Hub Standard footprint RESOLVED + AUTHORITATIVE
   (2026-06-05). The MPN is the Kinghelm KH-RJ45-58-8P8C (LCSC C2683360) — a single
   shielded 8P8C right-angle TH jack with metal-shell ground tabs. IMPORTANT: the
   prior "lead candidate" C86580 (CONNFLY DS1129-05-S80BP-X) was WRONG — pulling it
   showed it is a DUAL-port (16-contact, 31mm) jack, not the single-port the Hub's
   J2-J5 need. The C2683360 footprint was pulled via easyeda2kicad, upgraded to
   KiCad-10 format, and ORIGIN-ALIGNED so pad1 lands at (0,0) — i.e. the 8 contacts
   sit exactly on the legacy 1.27mm prepared land (pad1..8 = (0,0)..(8.89,-2.54)),
   so the existing contact routing is preserved; its two metal-shell ground tabs
   were renamed 9/10 -> SH1/SH2 to map to the symbol's shield pins (both GND). It
   REPLACED lib/cec.pretty/RJ45_FTP_Shielded_Horizontal.kicad_mod in place (same
   name -> J2-J5 need no schematic repoint), with the Kinghelm provenance in the
   footprint descr + the J2-J5 BOM props (LCSC C2683360). 3D model vendored at
   lib/3dmodels/Connector_RJ.3dshapes/. (The spec design-reference was the Wuerth
   615008137421 / C132217, but its real land is a 1.02mm pitch that does NOT match
   the board's 1.27mm routing — adopting it would force a full re-route of all 4
   jacks — and stock is thin (~166); Kinghelm was chosen as the drop-in, §2.1/OQ-37
   updated to match.) STILL PENDING (GUI): run "Update Footprints from Library" to
   pull the new geometry onto the placed J2-J5 — the 8 contacts stay connected,
   only the 2 shield tabs (SH1/SH2, both GND) need reconnecting per jack + a body/
   courtyard glance. EPS + 12VHPWR Standard now ALSO carry the FTP jack (SH1/SH2->GND);
   gen-modules.py emits it, so the 24-pin + the two PCIe SKUs pick it up on their next
   regen (still on the unshielded 54602 until then — compatible, single-end shield at the Hub).
3. Hub Standard PCB pre-fab layout pass (2026-06-04 review): the board is PLACED
   and FULLY ROUTED (DRC 0 unconnected), but a GUI pour/route pass remains before
   dropping DRAFT. (a) GROUND: only In1 is poured and it reads as fragmented
   (42 islands — almost certainly STALE FILL, since kicad-cli can't refill);
   first action is "Fill All Zones" (B) in the GUI and confirm In1 is ONE island.
   CAN_H/L and USB_D+/- are 100% on F.Cu over In1 with 0 vias (good); the slow
   lines (DETECT/LED/GPIO/EN) ride In2 directly under In1 (fine). (b) POWER:
   +5VSB/+3V3/USB_VBUS are routed as long thin traces on B.Cu — move to a F.Cu
   pour per LAYOUT-GUIDE; the 5VSB trunk (/5VSB_RAW 0.4mm) needs pour or >=1.5mm.
   DRC now reports 38 track_width errors on the power nets (surfaced only after
   the netclass-pattern fix below) — that IS the punch-list. (c) Pull CAN_RX/CAN_L
   in from the board edge (~0.03-0.13mm now → slot-antenna). (d) Tent the C1
   (4700uF) via-in-pad; add a 2nd GND via at D6 (USBLC6); silk cleanup on the
   RJ-45 shield pads + board-edge silk. NOT-a-bug (triaged): CAN 5V/3.3V "domain
   crossing" (TJA1051T/3 VIO=+3V3, correct); "no 120R" (split 60+60+4n7 present);
   U1 courtyard overlaps (antenna keepout, neighbors clear).

4. 12VHPWR Standard PCB finish (status 2026-06-05): high-current lanes routed
   (J3->shunt F.Cu, shunt->J4 B.Cu, all 6); lane 3 sense done (reference). 47
   ratlines remain — 6x INA OUT->ESP ADC (ISENSEP1-6) + Kelvin taps/RC-filter->INA
   on lanes 1,2,4,5,6. Before re-DRC: Fill All Zones (the 252 "actual 0.000mm"
   clearance/hole hits are STALE GND-pour, NOT real shorts), delete 18 dangling
   vias + 3 track stubs, Update-PCB-from-Schematic (syncs U2 value TJA1462A->
   TJA1051T/3, same SOIC-8 footprint; ALSO pulls the v3.7 NTC temp dividers
   TH1/TH2 + R20/R21 + C20/C21 — TH1 at the J3 +12V pins, TH2 ambient, into spare
   ADC2 IO13/IO14 — to place + route). Spec bumped to v3.7: OQ-8 RESOLVED (no local
   REF3033 on Standard — transient-capture tier, not precision); 12V input TVS and
   status LED considered and DECLINED (§6.1). The NTC dividers were hand-spliced
   into the routed schematic (ERC clean, netlist-verified TEMP1->IO13/TEMP2->IO14,
   all existing UUIDs preserved); gen-modules.py carries a note so a future regen
   does not drop them. Test points recommended ONLY if room
   (GND/+3V3/+5VSB/VRAIL_DIV/CAN_H/CAN_L) — add in the GUI, not the schematic
   (TestPoint symbol isn't embedded). Plan + diagram:
   modules/12vhpwr-standard/12vhpwr-route-plan.png (scripts/gen-hpwr-route-status.py).
   FEM PROBE FINDINGS (2026-06-09, adversarially verified; corrected for the model's
   segment-sum optimism — see the model-debt note below): balanced 600W (8.33A/pin)
   worst-lane dT ~+14C / 64C max (pass); connector-rating 9.2A/pin ~+18C / 68C (pass,
   ~1.7x margin to the 30C gate); a SUSTAINED 12A pin-hog (imbalance) puts the hog
   lane at ~+28-35C => ~78-85C — AT/OVER the 30C-rise gate, with the shunt-LO 6-via
   transition at J~85 A/mm2 (~15% under the sustained ceiling). GUI pour/route pass
   should therefore ALSO: (a) refill BOTH inner GND fills + stitch the J3/J4 GND
   barrel fields (the ~18mm funnel into 6 GND barrels is the real return constriction;
   plane-average +1.5C hides tens of C locally); (b) mirror the LO lanes onto F.Cu
   with stitching (the 45mm single-layer 2.5mm B.Cu run = 0.174mm2 is the board's
   longest narrow serial cut, first to flag at the 12A hog); (c) widen the F->B
   transition at each shunt LO pad + patch the lane-1 HI 0.063mm2 sliver at y~67.
   Detection thesis CONFIRMED by the probe: the 12A hog is a 58% instant electrical
   outlier on INA240 ch3 vs a lagging ~2.2C shunt thermal asymmetry — and at a
   sustained hog the electrical alarm also protects the module's own copper.
   MODEL DEBT (deliberate follow-up, NOT silently fixed — changes the SB-08 golden
   thermal band): electrothermal cross_mm2 SUMS all net segments (incl. zero-current
   Kelvin stubs) instead of the serial min-cut => lane dT ~5x optimistic; via split
   should be per transition cluster; IPC k is keyed to pour membership instead of the
   feature's actual layer. One fix LANDED (2026-06-09): the shunt I^2R current now
   reads the straddled net's current (honours net_currents overrides) instead of the
   40A per-cable default — essential on per-pin boards.

Done (kept for context):
- AGENTIC-PIPELINE PUNCHLIST + SELF-BUILDING FOUNDATION (2026-06-09, branch
  claude/agentic-pipeline-punchlist; spec v1.1.0 + R-05 landed earlier via PR #18 merge).
  Executed docs/agentic-pipeline-review-2026-06-09.md (R-*) + the first wave of
  docs/self-building-pipeline-addendum-2026-06-09.md (SB-*), every item VERIFIED on-device
  in the docker routing container (this box has NO host kicad-cli/pcbnew/java -- apt only
  has KiCad 7; the cec/routing:kicad10 container is the compute plane).
  * R-01 seed diversity: opt_spread=0 multi-seed now derives a 0.5x..1.5x opt_time spread
    (router + dispatch _spread_params; RESOLVED per-seed params recorded; sha256 dedupe
    before scoring). Verified: 4/4 distinct candidate hashes (was 4 identical).
  * R-02 single DRC: Metrics gains drc_types/drc_loci from the SAME run;
    cec_score.drc_types() for path-only callers; ONE cosmetic filter (cec_score);
    View.drc() feeds View.metrics; mkstemp temp files. Verified: 1 `pcb drc`/candidate.
  * R-03 CI gate: fab/<board>-* snapshot => ALWAYS checked (DRAFT override);
    hub-standard + 12vhpwr-standard graduated out of DRAFT (owner-approved); gate fails on
    ERROR severity only (CEC_SEVERITY_FLAGS; the all-severity red was 100% documented-benign
    warnings). Both boards ERROR-CLEAN; Actions confirmed ENABLED (644 runs).
  * R-04 verdicts on the run page ($GITHUB_STEP_SUMMARY, both workflows, both OSes);
    synth modes + the ===CEC_CANDIDATES_JSON=== marker contract documented in
    docs/self-hosted-router.md. R-06 prereqs (xvfb only on headless Linux). R-07
    atx-24pin-rev2 dispatchable (Quilter locked-placement caveat). R-08 dispatch CLI uses
    find_board + agent_route edge guards; tests/test_dispatch_loop.py 5/5.
  * R-05 toolchain degradation: scripts/cec_toolchain.py (dependency-free); DRC/ERC fail
    fast w/ install hint, netlist/render degrade. Full cascade runs tracebackless on a
    KiCad-less host. R-10 cec_route<->cec_router cross-notes; the stop-hook claim corrected
    (.gitignore is the backstop). R-11 README reconciled (boards/layout/tooling + v1.1.0).
  * SB-01 run ledger: scripts/cec_ledger.py -> SIBLING github.com/nathanfraske/cec-runs
    (private; owner decision) runs/ledger.jsonl; determinism manifest (KiCad pin + resolved
    kicad-cli, FR version, scripts SHA+dirty) embedded in EVERY decision log; router +
    run_pipeline append fail-safe; compose mounts /cec-runs. CEC_PARENT_RUN_ID threads
    restart lineage; `lineage` CLI reconstructs chains.
  * SB-08 golden regression: tests/golden/eps-8pin (frozen floorplan) +
    scripts/cec_golden.py (route w/ power pours -> score -> electrothermal; expectation
    BANDS in tests/golden/expectations.json; --freeze = human-approved band bump). Baseline:
    gates PASS, drc=4 finishing, 556 tracks/84 vias, max_T 128.2C. Teeth: a deliberate
    kelvin-gate bug -> FAIL exit 1. RUN IT (in-container) BEFORE MERGING scripts/** CHANGES.
  * SB-13/14 corpus: corpus/general/ (classes A/B/C/H, lifecycle, README schema; owner:
    stays OPEN, revisit at Class C) seeded w/ IPC-2221 k params + CAN/§6.6 Class B;
    scripts/cec_corpus_lint.py wired into checklist.sh (rejects sourceless/model-sourced/
    dup/Class-C-without-run-id; validates the project corpus' spec §refs still resolve in
    v1.1.0 -- mechanical SB-11 half). AUDIT: the 269-row corpus had FULL provenance already
    but 11 DOUBLE-EXTRACTED rules -> deduped to 258, unique deltas folded into kept rows.
  STILL OPEN (addendum later waves): SB-02 inbox (GitHub Issues queue), SB-03 footprint
  intake gate, SB-05 fab preflight, SB-07 firmware contracts (DECISION: location), SB-10
  policy-as-code, SB-11 full traceability map, R-09 finishing-filter structured matching,
  R-12 where='runner' GitHub-dispatch leg; SB-04/06/09/12 await hardware/history.
- PCIe KELVIN FIX + HIGH-CURRENT COPPER SYNTHESIZER + LLM BROKER (2026-06-09, commits 8fd02f9..9fbac79).
  Five-part session off the overnight run (which finished its 6.5h budget despite the Claude-RC
  disconnect: 63 routes, all EPS at the cosmetic floor, BOTH PCIe SKUs kelvin_ok=FALSE).
  (1) PCIe KELVIN GATE FIXED, both SKUs. Root cause: the PCIe shunt sat rot 90 with pad1(_HI) the LOWER
  terminal -> the INA238 Kelvin taps had to CROSS to reach it, FR stranded /SENSEC{N}_LO on the congested
  last cable. Same inversion EPS fixed (corpus rule shunt-rotation-hi-upper-terminal) but PCIe never got.
  Flipped gen-pcie-condensed.py shunt rot 90->270 (INA181 needed no change), regenerated both committed
  boards. VERIFIED: kelvin_ok F->T -- 2-port drc 20->4 obj 20754->4257, 3-port drc 12->2 obj 12766->4257.
  (2) MANAGER REPAIR REPERTOIRE (cec_router): default_manager now walks an extensible MANAGER_REPAIRS
  registry. place_rotate {ref,by} apply_edit primitive + kelvin_inversion_repair() (geometric perception:
  shunt HI/LO inverted vs the INA sense pads -> place_rotate RS{c} 180; identifies the shunt by TOTAL pad
  count==2 since the INA181 contributes 2 pads to the pair). Unit-tested + demonstrated AUTONOMOUSLY
  healing a re-inverted board (it1 rotate RS1, it2 rotate RS2 -> kelvin). logo_finishing_repair() written
  but NOT wired (a copper keepout cuts the GND plane -- needs the GND-assign approach).
  (3) FORCE-CORRIDOR ENFORCEMENT (cec_router._vital_keepouts_from_rules, rewritten): the old version only
  reserved _HI and centroid-skewed the column off-corridor (INA181 pad). New version reserves each cable's
  connector->shunt corridor (both _HI/_LO, clipped at the shunt so the inner-edge tap window stays open) ->
  FR routes signal AROUND it AND the tap is forced onto the shunt inner edge. In-pour redundant force
  traces 63->13, kelvin held, tap-off-inner 4->1.
  (4) HIGH-CURRENT COPPER SYNTHESIZER (cec_fr.synthesize_power_copper) + FEM. The real fix to "shunts
  connected by thin traces, not zones": Freerouting models a 40A net as a 0.2mm wire, so CONSTRUCT the
  power copper instead -- derive_power_pours corridor + a B.Cu mirror pour (ADD ONLY the missing layer, so
  the route's F.Cu stays; NEVER remove a zone -- zone removal corrupts pcbnew net info -> SwigPyObject) +
  derive_via_field stitching F<->B + real ZONE_FILLER + a SAFE conditional strip (reverts if it would
  disconnect). Wired through the electrothermal FEM (cec_synth_pipeline.physics). VERIFIED both SKUs:
  DRC-clean, kelvin_ok held, cross-section 0.10 -> 0.97-1.20 mm^2 (~10x), max_T 158->81C -- ~1C OVER the
  30C-rise budget at the thinnest neck. OPEN: a NOTCHED corridor keepout (exclude foreign from the FULL
  pour region except a tap notch) to clear the residual foreign-trace cuts -> full-width pour -> close the
  last neck; the shunt-PAD physical neck + 2-layer limit may still need the GUI 4-terminal Kelvin geometry.
  cec_constraints already has the checkers (high-current-pour-integrity / min-pour-cross-section /
  kelvin-sense-from-inner-pad) that flag exactly this; the corpus (scripts/constraints/corpus-extracted.json,
  269 rows) already encodes every rule -- the gap was ENFORCEMENT, now partly wired.
  (5) LLM BROKER. All local-LLM access defaults through cec-llm-broker (/home/nathan/cec-llm-broker, :8080)
  so this project and the other LLM project on the box don't thrash the single 5090. Routes by model name
  (cec-judge->:8000, cec-manager->:8001); cec_judge_local VLLM_URL default -> broker + X-CEC-Client header,
  cec_overnight host reviews -> broker, docker compose routing CEC_VLLM_URL -> host.docker.internal:8080
  + extra_hosts. Fail-safe (broker down -> deterministic fallback). Broker runs on 0.0.0.0:8080.
  UPDATED 2026-06-09 (same day, later session) -- BROKER v2 = MODEL ORCHESTRATOR: the broker now
  STARTS backends ON DEMAND from its models.json registry (start/stop commands, health URLs,
  vram_gb arbitration vs gpu_budget_gb on the single 5090 -- it SWAPS the conflicting model out,
  letting in-flight generations finish), rewrites alias->served names, lists the full catalog at
  GET /v1/models even with nothing running, and an IDLE REAPER stops backends after idle_stop_s
  (30 min default), freeing GPU+RAM automatically. NEVER compose up/down LLM services by hand --
  just request the model through :8080. MODEL LINEUP (2026-06-09 refresh; new GGUFs on
  "E:\AI Models" = /mnt/e/AI Models, old models kept in place): cec-worker = Qwen3.6-35B-A3B
  UD-Q4_K_M (VOLUME worker, 4 slots, :8002, alias local-model), cec-worker-quality = Qwen3.6-27B
  dense Q4_K_M (:8004, swap-in for max per-call quality), cec-manager = MiniMax-M2.7 229B-A10B
  UD-Q3_K_XL (:8003 -- Path C 2026-06-09: 102GB fits FULLY in page cache, MEASURED warm 12.9 tok/s
  = 3.5x the briefly-tried Q4_K_XL's 3.73 [141GB > RAM -> ~20GB expert rotation through 9p]; cold
  boot ~10.5min), cec-manager-fast = gpt-oss-120b MXFP4 (:8005, 5.1B active, experts-in-RAM ~6GB
  GPU, MEASURED warm 22.3 tok/s -- manager-class at ~6x the deep tier), cec-judge = the old vLLM
  30B AWQ (:8000, kept). The old 235B is RETIRED (2026-06-09, owner call: a remnant -- files
  deleted from the C:-backed VHDX [ext4 234->130GB used], registry entry removed; the Windows-side
  VHDX compact to hand C: back ~110GB is on the owner's todo). MEASURED worker tiers: cec-worker
  cold swap 90.7s, 4 CONCURRENT requests in 1.75s wall; cec-worker-quality 27B verified (thinking
  model -- WORKER_MAX_TOKENS 1200 covers it). Broker is now a systemd unit (survives WSL restarts).
  Verified live: on-demand cold start, GPU swap arbitration, queued-request ride-through on a
  10+min model load, idle reap (auto-stop + GPU back to baseline).
  TIER WIRING (2026-06-10, the post-bench "which model do we progress with" verdict, wired in).
  The 2026-06-09 reasoning bench (6 runs, hard quantitative trap problem): gpt-oss-120b ~9.5/10
  COMPLETE single-call (3.7k tok/172s) vs MiniMax-M2.7 truncating TWICE with EMPTY content (budget
  burned in reasoning_content at 8k AND 14k caps); M2.7's counter-win is adversarial AUDIT (its
  rumination surfaced a planted spec inconsistency oss-120b caught internally but OMITTED from its
  final answer). WIRED in cec_judge_local: (a) NEW out-of-loop REVIEWER tier -- corpus_fit_review
  runs on CEC_VLLM_REVIEWER_MODEL, default cec-manager-fast (explicit CEC_VLLM_MANAGER_MODEL pin
  honored second for back-compat); M2.7 is the opt-in deep AUDITOR (CEC_VLLM_REVIEWER_MODEL=
  cec-manager). The IN-LOOP manager tier deliberately KEEPS its worker-class default (panels
  interleave with worker calls every iteration; a big manager there = broker-swapping 27GB<->9GB
  models per iteration). (b) miner->scribe AUTO-RECOVERY in _chat_json: empty content +
  reasoning_content present -> a SCRIBE transcription call (same model, temp>=0.35 /
  presence_penalty 0.8 / json_schema grammar, trace TAIL-capped 36k chars for the 16k ctx) instead
  of the old silent deterministic fallback. (c) M2.7 SAMPLING FLOORS, model-conditional
  (_FLOOR_MODELS={cec-manager}): temp floored to 0.3 + presence_penalty 0.8 (verbatim decode-loop
  hazard -- the swarm panels send temp 0.0; the floor makes a M2.7 pin safe there). (d)
  cec_overnight modernized to BROKER-NATIVE lifecycle: the stale direct :8000/:8001 probes + hand
  compose stop/start swaps (targeting the gutted 235B `manager` service -- would crash-loop)
  replaced by broker-catalog `running` checks + a 1-token warm request; `routing` (compute, not
  LLM) is the only service compose still touches. Tests: tests/test_judge_local_scribe.py (8
  stub-server tests; host-runnable, no GPU). SB-08 golden PASS in-container post-change.
- TWO-TIER LOCAL JUDGE + CORPUS-FIT REVIEWER + OVERNIGHT DRIVER (2026-06-09). Thrust A control plane now
  runs on the workstation's own models (docs/local-compute-exploration.md "REALIZED"). (1) MANAGER tier:
  Qwen3-235B-A22B-Thinking-2507 GGUF Q3_K_M on llama.cpp (docker/compose.yaml `manager` :8001, profile-
  gated), "experts in RAM, attention on the 5090" via `-ngl 99 --n-cpu-moe 99` (11GB VRAM, ~4.3 tok/s,
  thinking-ONLY). MEASURED: a partial GPU expert offload (--n-cpu-moe 80) is SLOWER (2.7 tok/s, CPU<->GPU
  handoff overhead) + costs +15GB VRAM -> rejected; spec-decoding is the real decode lever, not offload.
  WORKER tier stays the fast vLLM 30B-A3B-AWQ (`inference` :8000). Single 5090 fits ONE
  heavy model -> they SWAP. (2) cec_judge_local: the manager tier got its OWN token budget (a thinking
  model overruns the worker's 400-default -> MANAGER_MAX_TOKENS 4096 / CEC_CORPUS_* knobs); `available()`
  takes a url. (3) `corpus_fit_review` -- deep per-board precedent-fit audit vs the same-family corpus
  (deterministic robust-z/MAD prepass -> compact evidence -> 235B critique; per-family scoping, <3-peer
  insufficient floor; fail-safe + add-only + a clamp so a gate-false board can't read "fits"). Verified
  live: caught trajectory THRASH on a layout-clean eps board, citing precedents by id. Wired into
  cec_router.route() (gated by CEC_CORPUS_REVIEW=1, writes a <board>-corpus-fit.json sidecar). (4)
  scripts/cec_overnight.py -- deadline-bounded driver alternating ROUTE blocks (worker up, routing in the
  `routing` container generating candidates) and REVIEW blocks (swap to manager, deep-review on the host).
  NOTE: routing needs pcbnew so it runs IN the routing container; corpus_fit_review is pcbnew-free and
  runs on the host. The local judge is opt-in (`--judge local`); the deterministic default is unchanged.
- AGENTIC DISPATCH PROTOTYPE -- compute-as-tools + a budgeted tier-escalation loop (2026-06-07).
  Per the user's design instinct (the two-plane router is "too detached": compute runs a blind batch,
  judgement happens after -> tighten the COUPLING so agents call compute on demand + defer up). scripts/
  cec_dispatch.py: (1) compute-as-TOOLS -- request_candidates(board, params, seeds, where) runs FR +
  scores + DRC-types and returns STRUCTURED METRICS (kelvin_ok/diffpair_ok/drc/unconnected/drc_types/
  loci) the agent reasons on, NOT raw boards (+ score_board, render); `where='local'` now, 'runner'
  (dispatch to synth.yml) is the TODO. (2) the budgeted LOOP agent_route(board, tiers, budget): request
  -> a TIER judges -> accept | request_more(new_params) [budget--, re-request] | escalate [defer UP,
  reset budget]; budget exhausted -> FORCED escalate (no thrash); ladder exhausted -> human. `tiers` =
  ordered decide(JudgeContext)->Verdict callables (Haiku swarm -> Sonnet -> Opus -> human); deterministic
  defaults run headless (loop unit-tested: accept-on-clean, request_more-improves, budget->escalate).
  KEY INSIGHT recorded: LLM inference and CPU compute are different resources -- 'consolidate' = couple
  them (compute-as-tools + a budgeted swarm that drives it), NOT co-locate. DEMONSTRATED LIVE end-to-end:
  request_candidates on EPS @passes5/opt5 -> both candidates kelvin_ok=True but diffpair_ok=FALSE (USB
  pair unrouted), drc=4 ALL on LOGO1. A real HAIKU sub-agent judge correctly distinguished the cosmetic
  logo DRC from the real diffpair-gate FAIL, judged it localized-not-structural, and returned
  request_more(passes=10,opt=15); the re-dispatch CONVERGED -> diffpair_ok=True, gates pass, DRC
  finishing-only -> accept. The agent drove the compute on demand, exactly the intended loop. NEXT: wire
  where='runner' (the Haiku swarm in the cloud dispatches the heavy route to the self-hosted runner);
  generalize the same loop to the cascade flags + the placement sweep; spawn a real PARALLEL Haiku swarm
  (one per region/candidate/flag). On branch claude/agent-dispatch.
- SYNTHESIS PIPELINE -- physics FEA + sign-off + build/freeze + run_pipeline = RUNNABLE END-TO-END
  (2026-06-07). (1) PHYSICS (analytic IPC, per user's choice): electrothermal_solve() -- per
  high-current net the parallel copper cross-section (tracks + pours, pour cut = area/path x
  thickness), the J->T->rho(T)->J Picard loop as a closed-form fixed point dT=dt0(1+a(amb-20))/(1-dt0a)
  with a runaway clamp (dt0*a>=0.95 = fusing) so a grossly over-current feature fails the gate not
  returns 1e40; dt_ipc() IPC-2221 closed form (k tunable to 2152); per-via split current + barrel
  cross-section; per-shunt I^2R; _net_currents() role model (cable=40A default, cfg-overridable);
  physics_gates() J/T/derating; wired the THERMAL armed-analysis to physics(). Verified on the routed+
  poured EPS @40A/enclosed: cable pours dT 18-46C (hottest the thinnest pour, T=96C), shunts 0.8W->20C,
  vias flagged FUSING (the §6.7/OQ-10 vertical-transition concern) -- 3 real thermal gates. (2) SIGN-OFF
  human_signoff() (cert-grade human rung; cautious headless = release only if nothing blocking). (3)
  BUILD+FREEZE freeze_build() (release board + frozen decision log = reproducible). (4) run_pipeline()
  THE TOP-LEVEL DRIVER on an EXISTING board (place/size DEFERRED): ERC+BOM gate -> triage -> existing
  board (opt route_swarm) -> physics+cascade loop (resolve on fail) -> sign-off -> build+freeze. CLI
  --run [--routed-board B] [--route]. VERIFIED end-to-end on the poured EPS: ran every stage and
  correctly WITHHELD release (residual DFM + conductor-over-temp + fusing-via flags) -- the cautious,
  defensible decision. THE PIPELINE IS NOW VIABLE END-TO-END (on the old-design board; the synth
  placer/size-oracle remains the deferred design-pass TODO -2).
  RUNNER (2026-06-07): (a) the self-hosted runner is VERIFIED LIVE -- a dispatched route.yml health
  check (run #13) was picked up + ran on the user's CEC-Workstation. (b) Fixed a real RUNNER BLOCKER:
  PCB_VIA.GetWidth() WITHOUT a layer asserts in KiCad 10; on the user's Windows debug build it pops a
  MODAL 'Debug Alert' dialog that blocks the runner -- cec_fr.normalize_via_annular now passes
  t.GetWidth(t.TopLayer()) (SetWidth and PCB_TRACK.GetWidth do NOT assert; only PCB_VIA.GetWidth(no-arg)
  does). (c) Added the SYNTH RUNNER DISPATCH: .github/workflows/synth.yml (workflow_dispatch, self-
  hosted cec-router, modes run|sweep) + scripts/synth.ps1 (Windows launcher mirroring route.ps1's
  KiCad-python+java discovery, runs cec_synth_pipeline.py). Committed on claude/synth-pipeline so it is
  DISPATCHABLE the moment this branch merges to main (workflow_dispatch needs the file on the default
  branch). STILL OPEN: merge the synth-pipeline branch to main; the deferred placer design pass; size
  oracle once the placer resumes.
- SYNTHESIS PIPELINE -- placer BEATS/MATCHES the bar, DRC-verified (2026-06-07). The overlap-vs-size
  sweep (per user: candidates are overlap-vs-SIZE, not min-overlap at one size) exposed that the real
  blocker was ANCHOR placement, not macros: two ~21mm cable connectors don't fit a 37mm board unless
  they OVERHANG (the user's exact ask). Implemented: seed_anchors() now seats connectors by their PAD
  BAND at the edge with the body/courtyard OFF-board (overhang), and packs multiple connectors on an
  edge by COURTYARD extent (not pad extent -- that left bodies overlapping). + place_mechanical mounts/
  fiducials nudged to free slots; + anneal_macros() SA on the macro positions (compaction + the
  diversity engine for best-of-N). RECURRING DRC-MISMATCH ROOT-CAUSED at last (the model kept under-
  counting vs kicad-cli): (a) the placer DROPPED the ESP antenna keepout but materialize embeds the
  FULL footprint -> now respects the keepout for DRC-consistency (the drop-keepout area win needs a
  trimmed-courtyard materialize, a follow-up); (b) the M3 mount courtyard PARSES DEGENERATE in
  cec_pcb (half 1.73x0.0) -> hardcoded a 3mm M3 keepout in _half_extent/_courtyard_info; (c)
  derive_passive_spec wrongly owned decoupling caps to BUTTONS (SW*) -> excluded buttons from owners
  (was the 2 SW1<->C21/C30 pad shorts). RESULT, REAL kicad-cli DRC (count now MATCHES DRC): 96x37 =
  courtyard 0 / short 0 -- FULLY CLEAN, matching the gen-eps-condensed bar, fully automated from the
  netlist + Stage-1 asks (overhang/mounts/fiducials/antenna); 88x36 (0.89x bar) = 1 courtyard, 0 short
  (essentially below the bar). LESSON RE-LEARNED + acted on: a placement's residual MUST be the real
  DRC (or pcbnew courtyards), never a self-reported bbox count -- root-caused 3 model-vs-DRC gaps this
  pass. STILL OPEN: push 88x36 to 0 (drop-keepout trimmed-materialize for the real area win + more
  sweep diversity); the considerations scoring (Kelvin/thermal/corridor/channels) as ranking terms;
  the huge runner sweep wired to synth.yml; fiducials not yet materialized; size oracle + FEA ahead.
- SYNTHESIS PIPELINE -- MACRO-BLOCK placer (auto_cluster) + generalized asks + perf cache (2026-06-07).
  The barycentric placer was 1.8x the area of my gen-eps-condensed board (the real bar -- that board
  is ALSO Opus-placed, not hand). Root cause: I drifted from the spec (place_with_consent =
  relative_place(ICs) + auto_cluster(passives)). Rebuilt to the spec + a MACRO-BLOCK model: derive each
  passive's owner IC from the netlist (derive_passive_spec, generalizing the hand PASSIVE_SPEC --
  signal-net coupling, pure-decoupling balanced across the rail; 26/26 EPS passives -> sensible owners),
  auto_cluster each IC's passives in ISOLATION to learn the cluster bbox + passive offsets, place the
  CLUSTERS by their full bbox (relative_place cyinfo_override) so the legalizer reserves the room, then
  stamp the passives rigidly. (Placing bare ICs tight then fanning passives into nonexistent gaps was the
  26-overlap/30-short failure.) _classify() splits anchors/ICs/shunts/passives; _count_overlaps() gives a
  DRC-ACCURATE residual (no more self-reported phantom-0). RESULT: density 1.8x -> ~1.12x bar, best
  residual 2 at 100x40 (12-candidate bulk), minimal + hand-finalizable. GENERALIZED ask-first Stage-1
  (per user -- not baked per-board): mount_holes / connector_overhang / fiducials added to REQUIREMENTS;
  place_mechanical() emits mounts (build_board mounts list) + fiducials from the asks. PERF: cec_pcb
  local_pads + courtyard_bbox MEMOIZED (_PADS_CACHE/_CRTYD_CACHE) -- auto_cluster's O(iters x parts^2)
  courtyard reads went from a hang to ~0.3s/candidate (pure cache, identical geometry, safe for all
  callers). Bulk candidate gen runs parallel on the spawn pool (runner-capable). STILL OPEN: not yet
  BEATING the bar (residual 0 at <=96x37 needs a compaction/anneal pass + structure-aware cable columns
  + a bigger bulk sweep); the considerations scoring (Kelvin/thermal/high-current-corridor/channels) not
  yet a ranking term; connector OVERHANG geometry + fiducial materialize still pending; size oracle +
  feasibility + FEA still ahead.
- SYNTHESIS PIPELINE -- Stage-1 human I/O + synth runner + placer-quality fix (2026-06-07).
  Per the user: (1) Stage-1 REQUIREMENTS elicitation -- elicit_requirements() + a REQUIREMENTS
  registry the orchestrator asks the human via AskUserQuestion (the human rung); answers recorded
  to cfg.params and wired through: antenna keepout (respect_antenna_keepout -> the placer trims the
  ESP32 courtyard 219->153mm2 via cec_pcb drop_keepout, AND EMC's RF arm only fires if the radio is
  populated), thermal_env (-> THERMAL arming + FEA derating), placement_handoff_mode, size_target.
  Collected the EPS answers live (wired-only, hand-off, enclosed/passive). (2) PLACEMENT HUMAN-HANDOFF
  -- place_finalize_handoff(): if the auto-placement isn't clean it materializes (cec_pcb.build_board)
  + renders the board and hands it to the human to finalize in the GUI before continuing (the user's
  step), or 'grow'/'proceed' per the mode. (3) SYNTH RUNNER -- run_sweep() (the headless runner-side
  compute: parallel place_candidates across sizes -> materialize + render + JSON report) + the CLI
  --sweep/--answers/--max-workers + (pending) a self-hosted synth.yml. (4) PLACER-QUALITY FIX (two
  real bugs the user caught from the render): the legalizer was point-relaxation that piled parts at
  high density -> replaced with legalize_pack() greedy nearest-free-slot (zero overlap by
  construction); AND it modelled each part as an ORIGIN-centred +-half box, but footprint origins are
  NOT the courtyard centre (asymmetric connector courtyards) and rotated anchors swap w/h -> now uses
  _courtyard_info() = the TRUE courtyard (centre offset + half at the placed rotation, from
  cec_pcb.courtyard_bbox) so the overlap test matches KiCad/DRC. DRC-VERIFIED on a materialized EPS
  synth board: courtyards_overlap 24->1 and shorting_items 7->0 at 125x52 (minimal, hand-finalizable).
  LESSON (added to my practice): verify a placement with REAL DRC before trusting a self-reported
  residual or a render. STILL OPEN (next, per the user): seed_anchors needs MOUNTING-HOLE handling
  (ask count/size/position -> footprint + placement; the synth board has none today) and CONNECTOR
  EDGE-OVERHANG logic (ask whether connectors hang off the edge to save area); plus the size oracle +
  feasibility probe + electrothermal FEA. NOTE: the EPS runs are BUILDING+TESTING the placer on the
  real EPS netlist as input -- NOT re-synthesizing the as-built EPS board (hand-designed, stays); a
  true top-down synthesis run (a new board) is where the full Stage-1 questionnaire fires.
- SYNTHESIS PIPELINE -- stages 2-3: size-oracle inputs + constructive placer (2026-06-07).
  Continued down the pipeline (deep-build, stage by stage). scripts/cec_synth_pipeline.py now
  also carries, all real + verified on EPS: (STAGE 2) read_placement() (pcbnew positions +
  courtyards + pad nets); packing_lower_bound() -- the geometric FLOOR, a true lower bound from
  total courtyard area + largest-part extent (NO efficiency divisor, which would inflate it above
  achievable sizes; EPS floor 86.6x33.4 / 2897mm2 sits below the as-built 96x37); placement_proxy()
  = hpwl() + rudy() (Rectangular Uniform wire DensitY congestion grid) + thermal_proxy() (per-part
  power binned -> hotspot); proxy_reject() -- a RELATIVE congestion gate (rejects when RUDY peak
  grows past baseline x factor as the board shrinks) + an absolute thermal-hotspot ceiling (a
  known-routable board with no baseline is NOT rejected); route_swarm() bridge wiring the pipeline's
  ROUTE SWARM stage onto cec_router.route() (real FR + gates + pour-after-route + decision log).
  (STAGE 3) the constructive PLACER (place_with_consent): seed_anchors() places connectors at edges
  by ROLE (power_in top / power_out bottom / host+usb right) + mounts at corners + honors user pins;
  relative_place() barycentric-places the rest by net connectivity (grid-seeded) under a strategy
  (dataflow / thermal_separated / compact) then legalize() (overlap relaxation); place_candidates()
  generates the strategy x seed variants on a PARALLEL spawn pool with max_workers (the runner-capable
  pattern from cec_fr -- per the user's call to let the packer use the runner CPU for a large candidate
  count); place_with_consent() picks best-by-proxy + runs the user-pin CONSENT loop (ask APPROVE/KEEP/
  EDIT rather than silently override a pin). VERIFIED: anchors land at the right edges, all 45 parts
  in-bounds, synth HPWL ~892 == the as-built 888 (connectivity captures the structure), residual
  overlaps fall as the board grows (the size oracle's 'too tight -> grow' signal), the spawn pool
  returns all candidates, the consent loop triggers on a binding pin. KNOWN LIMIT (honest): at ~80%
  part-area density the point-relaxation legalizer leaves residual courtyard overlap (the hand layout
  reaches 0 via structure) -- a shelf/row legalizer + structure-aware refinement is the noted next
  quality step; the route swarm + the cascade's re-place escalation also refine it. STILL TO BUILD:
  the FEASIBILITY probe (N low-effort cec_fr routes per candidate -> confidence; reuses the
  runner-capable parallel pool) + the SIZE ORACLE bisection, the top-level run_pipeline() driver, the
  electrothermal physics FEA, human sign-off, build+freeze. A self-hosted SYNTH workflow (like route.yml)
  so the packer/feasibility candidate sweep runs on the user's runner lands with the size oracle.
- SYNTHESIS PIPELINE -- stage 1: cascade + resolve backbone (2026-06-07). Began building the
  user's full board-SYNTHESIS pipeline (run_pipeline: Config -> ERC+BOM gate -> triage -> geometric
  floor -> place+proxy -> feasibility/size oracle -> ROUTE SWARM -> physics FEA -> full cascade ->
  gates+DRC -> sign-off -> build+freeze; POSTURE=CAUTIOUS, every failure/uncertainty calls resolve()).
  Per the user's choice (deep-build stage by stage; cascade+resolve FIRST -- it's the backbone every
  other stage hangs on), scripts/cec_synth_pipeline.py now carries, production-grade + verified on the
  real EPS module: (1) a real KiCad .net s-expr PARSER (Netlist: 45 comps / 54 nets on EPS); (2) the
  data model -- Config (board/profile/pins/params + artifact paths), Flag/Kind, Check, View (lazy
  netlist/DRC/ERC/score access); (3) the SIX marker-criteria STAGE LISTS, each REAL checks --
  ERC_BOM (erc/unconnected/power/CAN/JLC-BOM), PLACEMENT (courtyard/on-board via DRC), ROUTE_GATE
  (cec_score kelvin+diffpair hard gates + DRC + unconnected), MEASURE (Kelvin sense topology +
  rail-divider), DFM (width/annular/hole/clearance DRC), CONFORMANCE (the CLAUDE.md locked-decision
  suite: RJ-45-not-Mini-Fit on the link, pin allocation incl. pin7=reserved-not-AUX_REF, DETECT §2.3
  code resistor, §6.4 shunt values, RS-485 tiering, no module CAN term); (4) run_stage/
  run_full_cascade; (5) the OPTIONAL-analysis REGISTRY + triage_arm (EMC/THERMAL/PDN, cautious
  arm-on-doubt; EPS armed THERMAL+EMC); (6) the resolve() ESCALATION LADDER worker->manager->frontier
  ->human -- the LLM tiers are PLUGGABLE callables exactly like cec_router.make_subagent_policy
  (deterministic defaults run headless; supply tiers={'manager':fn,'frontier':fn}/ask=fn for the
  Opus/Sonnet sub-agents + the human consent rung). VERIFIED with teeth both ways: CONFORMANCE
  positively matches J1 RJ-45 / R1 2.2k DETECT / RS1,2 0.5mOhm / the full pin map; a forced wrong
  expectation FIRES; ROUTE_GATE FAILS on the unrouted floorplan (kelvin/diffpair/183 ratlines) and on
  the routed candidate the kelvin+diffpair HARD GATES PASS while drc/unconnected still report the 4
  logo + 2 shield finishing items (correct cautious gate). Run: python3 scripts/cec_synth_pipeline.py
  --board eps-8pin [--stage CONFORMANCE] [--resolve]. STILL TO BUILD (next stages, in pipeline order):
  the top-level run_pipeline() driver + ERC_BOM gate loop, geometric floor (packing_lower_bound),
  place+proxy+consent, feasibility probe + size oracle, route_swarm (wire onto cec_router.route),
  electrothermal physics FEA (electrothermal_solve Picard loop -- the biggest new subsystem), human
  sign-off, build+freeze. Diagram+pseudocode are the spec; this file is the orchestrator.
- ROUTE-TO-CLEAN + FULL AGENT-PIPELINE test (2026-06-06). Ran the whole automated routing system
  on EPS with the TIERED LLM control plane LIVE -- Opus planner/escalator (me) + a real Sonnet
  MANAGER sub-agent judging the candidates -- not the deterministic default policies. Findings:
  * EPS's persistent DRC=99 is NOT a Freerouting-effort problem (identical across an opt-time sweep
    10..300s) -- it is tool-pipeline artifacts. The Sonnet manager root-caused it (UUID-verified):
    49 annular_width + 46 via_dangling + 4 LOGO-related.
  * FIX 1 SHIPPED + VERIFIED: cec_fr.import_ses now FILLS the copper zones after the SES import
    (fill_zones=True). The SES import lays tracks/vias but never fills pours (only the real
    ZONE_FILLER does -- kicad-cli can't); without it every via into the GND plane reads as
    via_dangling and every plane pad as unconnected. EPS: structural DRC 99->53, unconnected 71->2
    (kelvin_ok + diffpair_ok still pass). island_removal_mode is honoured so islands drop per design.
    Also: cec_router write_once(spec.out, force=True) so a route is re-runnable to the same --out
    (the one-shot guard is for committed floorplans, not the router's own output dir).
  * MAJOR REVIEW FINDING -- TRACE SIZING IS NOT HONOURED: Freerouting IGNORES the netclass widths.
    The pcbnew Specctra DSN export is CORRECT (carries Power12V=2.5mm, Power/GND=0.5, Signal=0.22,
    via=0.9; net->class binding right: +3V3->Power, SENSEC*_HI->Power12V, etc.), but FR routes
    EVERYTHING at its 0.2mm track / 0.6mm via defaults. It slips past DRC only because the candidate
    is checked WITHOUT its .kicad_dru. A 12V net at 0.2mm is a fab disaster -- the real issue under 99.
  * DESIGN DIRECTION (per the user) -- HIGH-CURRENT = POURS, NOT FAT TRACES: (1) FR ignores widths
    anyway; (2) a 2.5mm trace won't fit channels FR routed at 0.2mm -- post-hoc widening COLLIDES
    (proven: the manager's post-hoc via-enlarge added +152 clearance violations); (3) current is
    carried by copper AREA. So GND (already a plane), the 12V SENSEC nets, and the power rails belong
    as FILLED POURS; FR routes only signal/control (0.2-0.25mm fine). This is a PLANNER/MANAGER
    judgement: classify each net {pour | wide-trace | signal-trace} from its current + the available
    space, and escalate a fat trace that can't route into a pour.
  * RESOLVED (2026-06-07) -- (a) POUR + (b) VIA ANNULAR both shipped into the toolkit, EPS now routes
    to a DRC=4 floor (gates pass), the 4 residual being only LOGO1 + the 2 shield-tab unconn (both
    placement/finishing, NOT routing). THE KEY INSIGHT was ORDERING: an earlier pass had concluded
    "pour breaks the Kelvin gate / needs a dedicated design pass" -- WRONG, that was a pour-THEN-route
    artifact (the pour reshaped FR's global solution so FR then failed to connect the sense out of the
    poured region; two attempts both regressed kelvin_ok). The fix is to pour AFTER the route: FR
    routes everything first (sense connected, gates pass), THEN lay the 12V pours as ADDITIVE same-net
    copper -- a pour on an already-routed net can only ADD copper, never strand the sense tap that
    shares the net node. New cec_fr helpers (all verified on the EPS FR candidate, gates stay
    kelvin_ok+diffpair_ok): `add_power_pours()` (additive same-net pours, ZONE_CONNECTION_FULL,
    ~120-150mm^2/cable @ ~1 island); `normalize_via_annular()` ((b) fix -- SHRINK the drill on
    thin-annular vias, keeping copper identical so NO new clearance; blanket via-ENLARGE was tried
    and made it worse, 53->82 DRC / +77 clearance); `derive_power_pours()` (auto-finds the pour rects
    from geometry = bbox of each cable net's THT-connector + 2-pad-shunt pads, INA sense pads excluded
    so HI/LO meet only through the shunt -- general across the EPS/PCIe interposer family, self-gating
    + safe no-op on boards without such nets). Wired through import_ses (fix_annular default on,
    power_pours param) -> route_once -> generate_batch -> Spec.power_pours; board_spec auto-derives.
    A FULL-MODEL-PIPELINE manager (Sonnet) pass judged the result ACCEPT (both gates pass; the 4 DRC +
    2 unconn are floorplan/finishing, owned by the placement pass). The routed board is a build
    artifact (build/route/, gitignored) -- the committed EPS floorplan stays no-pours (pours are a
    route-time step, not a floorplan edit). STILL OPEN (placement/finishing, unchanged): (c) LOGO1
    B.Cu no-via keepout / GND-assign (clears the 4); J1 SH1/SH2 shield-tab -> GND tie (the 2 unconn);
    and (d) WHY FR ignores the DSN per-class widths -- now MOOT for high current (pours carry it),
    still relevant if a wide signal trace is ever needed.
- AUTOMATED ROUTING SYSTEM — two-plane architecture (2026-06-06). Implemented the user's
  redesign: a DETERMINISTIC PLANE (reproducible, no LLM) under a CONTROL PLANE (tiered
  judgement, pluggable). Drives the REAL KiCad<->Freerouting autorouter via Specctra DSN/SES.
  Three new scripts (each self-tested):
  * scripts/cec_fr.py — Tier-0 Freerouting candidate GENERATOR. export_dsn (pcbnew
    ExportSpecctraDSN, 2-arg headless form) -> run_freerouting (xvfb-run java -jar the pinned
    **v1.7.0** jar, -mp/-oit/-mt, from a /tmp workdir so FR's logs/ never hits the repo) ->
    import_ses -> real routed copper. bake_hints() adds rule-area KEEP-OUT zones for vital
    areas (12V columns, Kelvin windows) that export into the DSN so FR routes AROUND them.
    generate_batch() = parallel candidates. CRITICAL GOTCHA FIXED: the pool MUST use the
    "spawn" start method, NOT the default "fork" — pcbnew/wxWidgets is NOT fork-safe, so a
    forked worker DEADLOCKS in __futex_wait at ExportSpecctraDSN once the parent has touched
    pcbnew (observed: 0 java ever launched, workers hung). spawn = fresh interpreter/worker,
    clean pcbnew re-import. Jar is NOT vendored (4.7MB binary); ensure_jar() downloads the
    pinned release or honours $CEC_FREEROUTING_JAR / /tmp/fr_1.7.0.jar / ~/.cache/cec/.
  * scripts/cec_score.py — metrics + HARD GATES. Rules.from_board() derives Kelvin pairs
    (*_HI/*_LO), diff pairs (*_P/*_N), 12V nets by convention. score()->Metrics(drc[structural,
    same cosmetic filter as cec_route.verify], unconnected, length, vias, tracks, kelvin_ok
    [GATE], diffpair_ok [GATE], cu12v, balance, gates_pass, detail). A pair passes only if BOTH
    members are routed (>=1 track) AND carry 0 unconnected ratlines. gate()->reasons;
    objective() ranks gate-passing candidates (lower=better).
  * scripts/cec_router.py — the route() ORCHESTRATION loop + DecisionLog + a CLI. spec_to_dru
    -> planner (regions+seam contracts) -> per-region {generate_batch -> score -> gate -> rank
    -> manager judge: accept|repair -> worker param/hint edit | escalator re-plan after Kmax
    stalls} -> serial_merge (seam reconcile: a crossing net is routed by its OWNER region only)
    -> write_once (one-shot guard) -> INDEPENDENT DRC verdict -> DecisionLog.to_json (replayable).
    apply_edit() does fr_params/keepout/seeds/place (placement edits via pcbnew — sanctioned).
    The four control-tier callables (planner/manager/worker/escalator) DEFAULT to deterministic
    policies so the whole thing runs end-to-end with NO LLM; the Opus/Sonnet/Haiku TIERS plug in
    via make_subagent_policy() (the orchestrator = Claude itself spawns the tier sub-agents for
    the harder judgements). CLI: `python3 scripts/cec_router.py --board <mod> --seeds 0,1,2,3
    --passes N --opt-time T --kmax K --max-iters M --out DIR --render`.
  VERIFIED on EPS: (a) a 4-seed batch routed 4/4 candidates in parallel (547 tracks each) under
  the spawn fix; (b) the full route() loop ran end-to-end (plan -> repair[sonnet] -> escalate
  after Kmax[opus] -> best-so-far -> merge -> independent DRC -> 4-entry decision log, 109s),
  result kelvin_ok=True + diffpair_ok=True (the HARD SAFETY GATES PASS — sense + USB diff pairs
  fully routed), DRC=99 (single-pass collision cleanup, the documented "not fab-clean yet"
  state the loop iterates against), 556 tracks/84 vias. ENV CEILING (this cloud box): 4 vCPU /
  15GB -> ~4 concurrent Freerouting runners (1 JVM/core, ~0.5GB each; cores cap, not RAM).
  Docs: scripts/README-cec_pcb.md ("Automated routing system" section).
- SELF-HOSTED ROUTING (run the CPU drain on the user's hardware, 2026-06-06). Per the user's
  choice, the compute plane can run on THEIR machine via a GitHub Actions self-hosted runner
  (the LLM control plane stays remote). .github/workflows/route.yml (workflow_dispatch only;
  runs-on [self-hosted, cec-router]) runs scripts/cec_router.py on the runner's CPU and uploads
  the routed candidate + decision log + render as artifacts; scripts/route-prereqs.sh fails fast
  if java/kicad-cli/pcbnew/xvfb are missing; docs/self-hosted-router.md = prereqs + runner
  registration (label cec-router) + how to trigger (UI/API/Claude session) + the security note
  (manual-only; never auto-run a self-hosted runner on untrusted fork PRs). Outputs land in
  build/route/<board>/ (gitignored). Ceiling scales with the runner's core count.
  CROSS-PLATFORM (Windows/Linux/macOS, 2026-06-06): made the compute plane portable. (1) xvfb is
  Linux-only — cec_fr._fr_command() wraps in xvfb-run ONLY on headless Linux (no $DISPLAY); on
  Windows/macOS (and Linux WITH $DISPLAY) it runs `java` directly (native display). (2) all
  scratch dirs use tempfile.gettempdir(), NOT a hardcoded /tmp (which is absent on Windows) —
  fixed across cec_fr/cec_score/cec_router/cec_route. (3) the worker pool's "spawn" start method
  is required on Windows anyway (no fork). (4) WINDOWS GOTCHA: pcbnew imports ONLY from KiCad's
  bundled python.exe — scripts/route.ps1 auto-discovers KiCad's python + kicad-cli + java and
  assembles PATH (so NO manual PATH config; only set $env:KICAD_PYTHON if KiCad is nonstandard),
  scripts/route-prereqs.ps1 is the Windows prereq check. (5) route.yml is OS-conditional (Windows
  step = Windows PowerShell `powershell -ExecutionPolicy Bypass -File {0}` + route.ps1; Linux/mac =
  bash + cec_router.py). (6) Windows reliability note: no
  xvfb means Freerouting needs a real desktop, so the Windows runner must run INTERACTIVELY (run.cmd
  in a logged-on session / Task Scheduler "run only when user is logged on"), NOT as a Session-0
  service; a Linux runner can stay a headless service (xvfb). Full Windows setup +
  the "do I need to configure PATH? -> no" answer in docs/self-hosted-router.md.
- WINDOWS RUNNER VERIFIED + STRESS-TESTED (2026-06-06, PR #6): the self-hosted Windows path is LIVE
  and verified on the user's runner (CEC-Workstation, i7-13700K; KiCad 10 + JRE 21). Reaching a green
  run fixed a cascade of REAL first-run Windows issues (all on main now): (a) shell: pwsh ->
  `powershell -ExecutionPolicy Bypass -File "{0}"` -- PowerShell 7 isn't installed by default AND a
  fresh runner's Restricted execution policy blocks every .ps1; (b) KiCad discovery HARDENED in
  route.ps1/route-prereqs.ps1 (KICAD_PYTHON -> kicad-cli on PATH -> the uninstall-registry
  InstallLocation -> Program Files\KiCad + \KiCad on EVERY fixed drive) -- the user's KiCad is a
  PER-USER install at C:\Users\<u>\AppData\Local\Programs\KiCad, NOT C:\Program Files, now auto-found
  (no manual PATH); (c) route.ps1 $ErrorActionPreference = Continue -- under Stop, Windows PowerShell
  turns a native tool's stderr (java -version, python) into a terminating NativeCommandError;
  (d) Freerouting launched MINIMIZED + no console (subprocess STARTUPINFO SW_SHOWMINNOACTIVE +
  CREATE_NO_WINDOW) so its Java window (no xvfb on Windows) doesn't steal focus, with the
  ForegroundLockTimeout backstop in docs/self-hosted-router.md. VERIFIED: a full eps-8pin route ran
  end-to-end ON THE RUNNER -- kelvin_ok + diffpair_ok PASS, 556 tracks/84 vias, DRC 99, 5-file
  artifact uploaded.
  STRESS (max_workers knob + parallelism logging, PR #6; route.yml max_workers input / --max-workers /
  route.ps1 -MaxWorkers; 0=auto=min(seeds,nproc)): 24 seeds @ auto routed 24/24 candidates in parallel
  (24 Freerouting JVMs on the 24 threads), ~2:25 route step, gates pass. PUSHING PAST the thread count
  LOCKED THE MACHINE: 48 seeds @ max_workers=48 (2x oversubscribed, ~24GB of JVMs) thrashed the
  i7-13700K into a hard lockup. CEILING: cores cap throughput, RAM caps the JVM count, and they
  collide at the logical-CPU count -- **24 is the cap on this runner**. generate_batch now WARNS when
  workers > CPU threads; keep max_workers at 0 (auto) or <= thread count.
- PCBNEW REAL-COPPER ROUTING TOOLKIT scripts/cec_route.py + sub-agent routing pass GO-AHEAD
  (2026-06-06). pcbnew (the real KiCad 10.0.3 Python engine) IS available in this env and can
  do what kicad-cli cannot: create real (segment)/(via) copper and FILL pours via the real
  ZONE_FILLER. cec_route.py = a Router(path) wrapping it: .pad(ref,num) / .track(net,pts,layer,
  width) / .via(net,at,drill,dia,layers) / .zone(net,poly,layers...) / .fill()->bool /
  .save() / .verify()->{n_struct, structural[], n_unconnected, unconnected[]} (verify saves +
  runs the real kicad-cli DRC, filters benign lib_footprint_* + silk). Smoke-tested on EPS:
  fills the GND inner-plane zone + lays a track + via -> 0 real structural, 160 unrouted
  ratlines (expected). The GO-AHEAD (added to "What Claude should do/NOT do"): real routing is
  now sanctioned PROGRAMMATICALLY via this toolkit as a SUB-AGENT routing pass (orchestrator
  builds/spawns, never hand-routes); hand-poking track s-expr text stays banned. Workflow loop:
  placement pass -> game-plan pass -> ROUTING pass (cec_route, real copper on a COPY, routes the
  deterministic nets clean + attempts the spine) -> snag report that feeds back precise changes
  to the footprint/placement pass AND the game-plan pass -> revise -> re-route. Deterministic
  nets (12V pours filled+split, GND stitch, Kelvin, USB diff pair, CAN, short P2P) route clean
  headlessly; the dense crossing spine may need a placement/plan change, Freerouting via DSN
  (java present, jar not), or the GUI.
  DEMONSTRATION DONE (routing sub-agent on EPS, candidate at /tmp/eps-routed/): routed the
  deterministic CORE as real copper at 0 structural DRC -- GND inner-plane fill + stitch vias,
  the 8 split 12V pours (filled, F+B mirrored), and the USB diff pair (with a D+/D- via-swap for
  the J5<->U1 side crossover). The pass closed the loop with precise feedback: (toolkit) it
  FOUND TWO REAL BUGS in cec_route.py -- zone() must append into z.Outline() in place (SetOutline
  aliases an external SHAPE_POLY_SET -> empty outline -> ZONE_FILLER segfault) and fill() must
  z.UnFill() before re-filling -- BOTH NOW FIXED + tested (real pour fills 54.88mm^2, double-fill
  in one process, 0 segfault); (->placement) move U2 next to the ESP CAN pins (it's top-right,
  CAN_TX/RX cross the whole board), move the B.Cu CEC LOGO off the ESP underside (it blocks the
  natural B.Cu escape), rotate INA181 U20/U21 180 / nudge C20/C21 so the Kelvin LO escapes,
  fix the shunt HI-below-LO inversion that crosses the INA238 taps, widen the mid-board signal
  channel ~2mm; (->game-plan) the "y17 open lane" for the spine is FALSE (occupied by ESP body
  y12-32 + LDO + INA pad rows) -- respec to the y20.6-23.6 band with B.Cu hops over the ESP,
  split the 6 spine nets across F.Cu/B.Cu, call out the USB side-swap + run CAN_H/L down the far
  right edge to dodge DETECT J1.8. The dense spine is the open item (placement/plan revision, or
  Freerouting/GUI) = the "stretch its legs" next iteration.
  LOOP ITERATION 2 DONE (2026-06-06): the feedback was fed back through the sub-agent passes --
  a REVISION pass applied it to the EPS driver (H 35->37 wider spine channel; shunt rot 90->270 so
  HI is the upper terminal -> Kelvin no longer crosses; INA181 rot 0->180; U2 moved by the ESP CAN
  pads w/ C3/C6 displaced; CEC logo moved off the ESP underside -> B.Cu freed; spine re-spec'd to
  the y22-25 band, I2C on F.Cu / THRESH+DETC on B.Cu, USB side-swap, CAN far-right) at 0 structural
  DRC (commit 14906cc, 96x37mm), then a 2nd ROUTING pass re-routed it. RESULT: the open question
  CLOSED -- the control->sense spine now ROUTES TO REAL COPPER (THRESH/DETC/DETAMP all 0 ratlines;
  unconnected 119->23; Kelvin taps confirmed non-crossing). DRC went 92->343 because it routes ALL
  28 nets in one dense single-pass (collision cleanup, NOT unroutability: ~187 of 343 are
  power-net-involved). NEXT BLOCKER is no longer the spine -- it's POWER DISTRIBUTION (+3V3/+5VSB/GND)
  + right-cluster density (U2/U3/cap-field packed x62-86,y8-20), which wants a placement-relax pass +
  an explicit power-routing game-plan, or a Freerouting/GUI rip-up/reflow that single-pass scripting
  can't do. The loop (route -> snag -> revise -> re-route) is proven end-to-end; candidate at
  /tmp/eps-routed2/ is the routed-core+spine demo, NOT a fab-clean board.
- REPO-WIDE PCB LAYOUT TOOLKIT scripts/cec_pcb.py (2026-06-06). Refined the EPS candidate
  generator into a shared toolkit ANY board generator / agent can pull on (does NOT modify
  the shared gen-module-pcb.py -- it imports its emit primitives once via the no-op-filter
  trick). Abilities: GEOMETRY (pad_global / courtyard_bbox / part_half, KiCad-rotation
  correct, with an RF antenna-keepout trim); PASSIVES (verify_passives netlist ownership
  check; auto_cluster = geometry-driven decoupling placement -- parks each cap outside its
  owner IC's power-pad, courtyard-aware + fanned + overlap-relaxation, returns residual
  overlaps; place_offsets for hand-refined coords); ROUTING guides() (12V pours / Kelvin /
  spine / CAN / USB guide graphics on toggleable user layers, in-board, non-copper);
  routing_plan_png() (board-accurate matplotlib plan); netclass()/write_netclasses()/
  write_dru() (fill an empty .kicad_pro net_settings + matching .kicad_dru); build_board()
  (assemble the .kicad_pcb with the one-shot routed-board guard). gen-eps-condensed.py is
  now a THIN driver = the worked example (supplies only EPS data; ships place_offsets by
  default at 0 structural DRC reproducing the committed board EXACTLY, exposes auto_cluster
  behind --auto which placed all 25 EPS passives at 0 residual overlaps). Usage guide:
  scripts/README-cec_pcb.md. matplotlib+PIL available. Reuse it on the PCIe SKUs (same
  i2c-cable family) and any module that needs passive clustering / routing candidates /
  netclasses.
- PCIe cable connector LOCKED to the REAL Molex 45586 (2026-06-06). The user confirmed
  the PCIe 8-pin header is Molex 45586-0005 (Mini-Fit Jr. dual-row RIGHT-ANGLE, 3rd-gen
  PCIe polarization, 8 circuits, Nylon UL94V-0, 2.54um matte tin) and uploaded the Molex
  ECAD export (TraceParts -SD footprint + STEP). Vendored the manufacturer land as
  lib/vendor/Connector_Molex.pretty/Molex_Mini-Fit_Jr_45586_2x04_P4.20mm_Horizontal.kicad_mod
  (kicad-cli fp upgrade to KiCad-10) + lib/3dmodels/Connector_Molex.3dshapes/<same>.step.
  REAL land: 4.20mm pitch + **5.50mm ROWS**, round 2.3622mm pads / 1.8542mm drill, two
  3.048mm snap pegs at native (0,7.3)/(-12.6,7.3) in line with the outer pins.
  (CORRECTION 2026-06-06: the TraceParts -SD export auto-derived the row spacing as 4.20mm
  — a square-grid error — and that wrong value first shipped; the user flagged it against
  the sheets. Real Mini-Fit Jr RA row-to-row is 5.50mm. Pads 5-8 moved to y-5.5, courtyard
  pad-edge to -6.935.) The footprint is native mouth-toward-+y with pads running -x, so the
  PCB generator places J_IN rot180 / J_OUT rot0 — reproducing the same pad x-columns +
  numbering as before, so the net map + 12V alignment are unchanged. PCIe-2/3 SCHEMATICS are
  hand-repointed to this land + J_IN/J_OUT sourced (Manufacturer=Molex, MPN=45586-0005; THT,
  consigned, no LCSC); the PCBs regenerate from those via gen-module-pcb.py (99x44 / 126x44,
  DRC 0 structural, pads+pegs on-board, render confirms). NOTE: this PCIe connector work is
  DETACHED from the EPS module (being hand-edited in parallel). gen-modules.py's CEC_CONN_2x4
  footprint default is left as the user has it; the EPS's own EPS12V-keyed connector (Molex
  87427-0802, a separate land) and any per-board generator mapping are the EPS work's domain.
- PCIe CONDENSED CANDIDATE GENERATOR — both SKUs, EPS methodology w/ sub-agents (2026-06-06).
  scripts/gen-pcie-condensed.py is the **parametric** PCIe analogue of gen-eps-condensed.py:
  ONE generator drives both SKUs by board-name arg (pcie-8pin-2port N=2, pcie-8pin-3port N=3),
  reuses gen-module-pcb.py's emit helpers via the no-op-filter import, does NOT modify the
  shared generator, writes ONLY the PCIe dirs — DETACHED from the parallel EPS work. Built the
  EPS way via **two sub-agent passes**: (1) FOOTPRINT/PLACEMENT planning -> explicit DRC-clean
  frame + PASSIVE_SPEC + cluster coords (superseding the earlier runtime packer; deterministic
  + reviewable); (2) ROUTING GAME-PLAN -> routing_guides() guide graphics on user layers (12V
  pours Dwgs.User / Kelvin Cmts.User / +3V3-I2C-THRESH-DET spine Eco1.User / CAN-USB Eco2.User,
  all pad-derived) + matplotlib pcie{2,3}-routing-plan.png. Sizes: **2-port 86.4x44 (pitch 23),
  3-port 103.4x44 (pitch 20)**. 3-MOUNT scheme (per user): TWO on the logic/right side (TR/BR
  corners) + ONE centered on the connector/left side at (4,H/2) — matches the 2-port arrangement;
  CX0=11 left margin opens the clear band between J_IN/J_OUT for the centered mount (that margin
  is why the 3-port is 103.4 not the 99 of the 2-mount sub-100 variant — PCB-area cost negligible
  per the BOM delta analysis: the 3rd port is ~$5.5/board, all sensing channel, ~$0 board). Frame:
  cables J_IN rot180 / J_OUT rot0 (45586, pegs keep H=44), sense band INA238|shunt|INA181/TLV7011
  spread to clear; core ESP32-C6 (antenna keepout dropped), CAN, LDO, RJ-45 (mouth overhangs right)
  / USB-C front end. PASSIVE_SPEC verify: 28/28 (3-port), 25/25 (2-port — the 3rd-cable C12/C22/C32
  correctly absent). Both DRC 0 structural except 1 known headless false SW2 mask-bridge artifact
  (geometrically impossible; absent in GUI). DET cable-3 -> ESP IO7/pad16 (not a 28/29/30 sequence)
  — keyed correctly. Render + DRC verified both. One-shot bootstrap (refuses to overwrite once
  routed; --force). Run: python3 scripts/gen-pcie-condensed.py <board> [--no-plan|--force].
  SUPERSEDES the earlier single-board gen-pcie3-condensed.py (removed) and the prior shared-gen
  99x44 2-port floorplan.
- 12VHPWR Standard BOM fully sourced for JLCPCB + datasheet pinout pass (2026-06-06).
  All 26 unique lines carry LCSC/MPN/Manufacturer in the schematic symbols (edit via
  the bom skill); outputs in modules/12vhpwr-standard/bom/ (bom.csv + 12vhpwr-standard-
  BOM-jlcpcb.csv). ~$21/board JLC parts (single-qty) under the $49 target; cost driven
  by 6x INA240A3DR ($1.87, C2060584 = the SOIC-8 **D** part, never PW) + ESP32
  (C3013941) + 6x 1mΩ shunt. D1 corrected PESD5V0S1UL->PESD5V0S1BA (C5261083). Pinouts
  datasheet-verified (INA240 SBOS662C / LP5907 SNVS798Q / ESP32-S3-MINI-1 Table 3-1 /
  REF3030 SBOS392K / TJA1051 NXP — all symbol pin maps correct; netlist unchanged,
  85 nets/312 nodes, ERC still only the benign lib_symbol_mismatch). FLAGS: J3/J4
  12V-2x6 (Molex 2191161161) NOT in JLC catalog -> consigned (no LCSC, by design; J4 is
  a pigtail); RS1-6 shunt
  CSS2H-2512R-1L00F (C4175647) is the spec §6.4 candidate but OQ-11 still OPEN (not
  locked; flagged per-RS Note prop). CPL/gerbers
  pending the GUI PCB finish; datasheet-URL props not yet populated.
  THEN (2026-06-06, 2nd pass, per user) swapped J1 + SW1/2 to the Hub's already-sourced
  parts: J1 -> shielded FTP Kinghelm KH-RJ45-58-8P8C (C2683360, cec:RJ45_FTP_Shielded_
  Horizontal) -- moves 12VHPWR-Std to the §2.1 platform FTP jack AND retires the old 54602
  (C2847314, JLC stock was ~7). DROP-IN on the routed land: pads 1-8 are pad-identical
  (1.27mm, (0,0)..(8.89,-2.54)) so the contacts stay routed; committer just runs Update-
  Footprints-from-Library on J1 (mounting pegs ~0.1mm off = same holes now NPTH; 2 new
  shield-tab pads). Shield SH1/SH2 TIED TO GND (both ends shielded AND grounded, per user --
  Hub+module share the PC chassis on a short RJ-45 so both-end grounding wins at HF, ground
  loop negligible via the M3-mount chassis bond); wired in the sch (3 wires + GND #PWR926 +
  junction at J1's right edge, ERC clean, SH1/SH2 now on GND net 98->100 nodes), committer
  ties the 2 tabs into the GND pour on Update-Footprints-from-Library. SW1/2 -> TS-1088-
  AR02016 (C720477, XKB, Basic) like the Hub -- land CHANGES (EVQ 4-pad -> TS-1088 2-pad),
  NOT a drop-in, so the committer re-places + re-routes the 2 buttons. Both done in the
  schematic (ERC clean, netlist unchanged 85 nets); PCB Update-from-Library pending in GUI.
  THEN (2026-06-06, diff-pair prep) renamed the 6 INA-input pairs /INPP{n}->/IN{n}_P and
  /INNP{n}->/IN{n}_N so KiCad's differential-pair router auto-recognizes them (suffix _P/_N);
  pure label rename (UUIDs/positions preserved, ERC clean, netlist node-set identical, only
  the net NAME changes). Repointed the .kicad_pro Sense netclass patterns /INPP*->/IN*_P and
  /INNP*->/IN*_N (Sense already carries diff_pair_width 0.25 / gap 0.2). The committer then
  Update-from-Schematic, rips up the IN+/- on each lane, and routes with the diff-pair router
  (shortcut 6) for a tight matched pair (skew-tune optional -- it's a near-DC sense pair, the
  win is small loop area, not ps skew). The pre-filter taps (/SENSEP*_HI/_LO) share the 12V
  force net so they stay hand-routed.
  ALSO (2026-06-06, parity w/ PCB) moved the 47k/10k rail-divider input R5.1 from SENSEP1_HI
  -> SENSEP6_HI (pin-6 HI, closest to the ESP) -- electrically identical (all 6 +12V pins are
  the same rail), just shorter routing. One-label change (UUID preserved); divider output
  VRAIL_DIV->R6->GND and ->IO7 unchanged, ERC clean.
  ALSO (2026-06-06, tolerance fix) the rail divider R5/R6 carry Tolerance=0.1% (v3.8 spec)
  but had been mis-sourced to 1% UNI-ROYAL 0402WGF parts -- the REF3030 ratiometric ref does
  NOT cancel divider-ratio error, so 0.1% is required for the ~0.3-0.5% V channel. Repointed
  R5 -> Yageo RT0402BRD0747KL (C728561, 47k 0.1% 25ppm) and R6 -> RT0402BRD0710KL (C190095,
  10k 0.1% 25ppm); same 0402 land, BOM regen. (R2/R20/R21 are also 10k but stay 1% C25744 --
  pullup/NTC, not precision.) Review follow-ups: VRAIL_DIV ADC cap DONE 2026-06-06 -- added
  C24 = 1nF C0G (Murata GRM1555C1H102JA01D / C76947) VRAIL_DIV->GND, fc~19kHz with the 47k||10k
  source (matches the ~16.9kHz INA channels) + serves the ESP SAR S&H; spliced near R6 at
  (107.95,270.51), ERC clean, netlist VRAIL_DIV={C24.1,R5.2,R6.1,U1.11}. STILL OPEN: the 6
  ISENSEP INA outputs have no ADC-input cap (INA drives direct, optional); RFH/RFL filter
  10ohm DONE 2026-06-06 -> 0.1% Yageo RT0402BRE0710RL (C705642, 0.1%/50ppm) on all 12 for AC
  CMRR on the transient capture (same R_0402 land, drop-in); RS
  shunt OQ-11 still open (CSS2H-2512R-1L00F candidate, +/-1%/75ppm); fiducials DONE 2026-06-06 (3x cec-Fiducial:Fiducial_1mm_Mask2mm, board_only/excl-BOM/excl-pos,
  refs on F.Fab: FID1 (162.25,61) TR, FID2 (166,135.5) BR, FID3 (139,116) lower-center; DRC copper-clean).
- EPS 8-pin NETCLASSES + .kicad_dru + USB diff-pair (2026-06-06). The previously-empty
  eps8pin-module.kicad_pro now carries 7 netclasses (Power12V 2.5mm pour via0.9/0.5 clr0.2
  /SENSEC*; GND 0.5 via0.9/0.5; Power 0.5 via0.8/0.4 +3V3/+5VSB/VBUS; Signal 0.22
  I2C/THRESH/DET/CAN_TX,RX/EN/CC; CAN 0.25 coupled /CAN_H,/CAN_L; USB 0.25 diff gap0.13
  /USB_D_P,/USB_D_N) + a matching eps8pin-module.kicad_dru (Power 0.5mm floor, USB diff-pair
  gap, explicit NO floor on /SENSEC* so the pour + the shunt-shared Kelvin taps aren't
  false-flagged). MATCHED PAIRS: USB is now an AUTO-RECOGNIZED diff pair -- renamed the
  schematic labels /USB_DP->/USB_D_P, /USB_DM->/USB_D_N (repo _P/_N convention; ERC clean,
  connectivity identical D+={J5.A6,B6,U1.18} / D-={J5.A7,B7,U1.17}); CAN_H/CAN_L KEEP the
  standard (asymmetric) names and route as a coupled pair; the Kelvin sense is hand-matched
  (shares the /SENSEC* force net, can't be a separable diff-pair). Power12V clearance set to
  0.2 (not 0.25) because the INA238 Kelvin inputs ARE the /SENSEC* nets entering a 0.5mm-pitch
  VSSOP-10 -- the 24-pin DRU precedent. DRC 0 structural with all rules active. Board regen'd
  for the new USB net names; gen-eps-condensed.py netclass-table text updated.
- EPS 8-pin CANDIDATE GENERATOR + routing plan (2026-06-06). scripts/gen-eps-condensed.py
  now PRODUCES the condensed floorplan reproducibly (reuses gen-module-pcb.py's emit helpers
  via a no-op-filter import; does NOT modify the shared generator). Three parts: (1) FRAME =
  the pegless-87427 condensed layout; (2) PASSIVE ENGINE = every decoupling/RC/pull-up/ESD
  passive placed in its OWNER IC's cluster from a netlist-verified ownership spec
  (PASSIVE_SPEC: part->IC->expected net), re-checked at build by verify_passives() (25/25
  verified) so clusters can't drift from the schematic; reproduces the committed placement
  EXACTLY (0 position diffs) at 0 structural DRC; (3) ROUTING CANDIDATES drawn in-board on
  toggleable user layers (12V pours Dwgs.User, Kelvin pairs Cmts.User, +3V3/I2C/THRESH/DETC
  spine Eco1.User, CAN/USB Eco2.User) + a board-accurate matplotlib eps-routing-plan.png (the
  pours, GND stitch, Kelvin, spine, CAN, USB over the real placement, with routing order 1-9,
  the netclass table for the empty .kicad_pro, and SI keep-aways). Built from the two
  sub-agent specs (passive placement + routing game-plan). One-shot bootstrap: refuses to
  overwrite once tracks/vias exist (--force overrides). Routing guides are non-copper -> no
  DRC impact. Run: python3 scripts/gen-eps-condensed.py [--no-plan].
- EPS 8-pin PCB RE-CONDENSED on the pegless 87427 (2026-06-06). With the snap pegs gone
  (87427-0802 has none), re-floorplanned 99x44 -> **96x35mm (-24% area, ~-20% height)**: the
  pegless connector keeps only its pad rows on-board and overhangs the whole body/mouth, so
  J_IN/J_OUT pull to ~4mm from the top/bottom edges (cable column ~22->~14mm). Connector
  rotations FLIP (87427 is mirrored): **J_IN rot180 / J_OUT rot0** (was rot0/rot180), J_OUT at
  Xc+12.6 keeps the +12V columns aligned for a straight vertical shunt path. ALL 45 schematic
  parts placed (decoupling no longer waits for Update-from-Schematic); 0 STRUCTURAL DRC (only
  cosmetic silk + benign lib_footprint_mismatch). ESP32-C6 antenna keepout DROPPED (no wireless,
  per user) -> GND fills under it, courtyard trimmed to body. 3 M3 mounts (2 left strip, 1
  bottom-right below the RJ-45). Render + DRC verified. Made by a one-shot condensed-placement
  pass reusing gen-module-pcb.py helpers (NOT folded into the shared generator, per user's
  "adopt it" choice); hand-maintained in the GUI from here. Routing candidates (12V outer pours
  split at shunt / dual inner GND / Kelvin off shunt inner edges / control->sense spine on the
  mid-height outers / short CAN+USB in the core) are written into the EPS README.
- EPS 8-pin power-connector pinout fix + formal Molex footprint (2026-06-06, per user
  cross-check). The interposer's 4 Mini-Fit Jr connectors (J_IN1/J_OUT1/J_IN2/J_OUT2) had
  +12V on pads 1-4 / GND on 5-8 -- the FLIPPED assignment vs the EPS12V/EATX12V standard.
  Corrected to **GND on pads 1-4, +12V on pads 5-8** in the schematic (netlist-verified all
  4: pins1-4=GND, pins5-8=SENSE*_HI on J_IN / SENSE*_LO on J_OUT; shunt path + §6.13 INA181
  taps unchanged -- they tap the SENSE nets, not pins) AND at the source in gen-modules.py
  (PINMAP["eps-8pin"] 12V:[1,2,3,4]->[5,6,7,8], GND:[5,6,7,8]->[1,2,3,4]; PCIe's separate
  entry untouched) so a regen won't revert it. Footprint repointed from the approximate
  generic 5569-08A2 to the **official Molex 87427-0802** RA header (vendored
  cec-Connector_Molex:Molex_Mini-Fit_Jr_87427-0802_2x04_P4.20mm_RA + 874270802 STEP; the
  modern part used on newer boards). NOTE the 87427 export has NO snap-peg NPTH holes (the
  old 5569-08A2 had two at y-4.2) and is MIRRORED (pads in -x, 2nd row -y, body +y), so the
  PCB committer must Update-from-Schematic and RE-PLACE/re-route all 4 connectors + re-derive
  the floorplan edge overhang (retention now via THT tails, not pegs). gen-modules.py's
  SHARED footprint default (M["CEC_CONN_2x4"], line 139) still points at 5569-08A2 (PCIe
  also uses it) -- the EPS schematic carries the 87427 by hand; a per-module footprint
  override is the follow-up if EPS should emit it on regen. ERC unchanged (2 pre-existing
  errors + benign noise).
- EPS 8-pin module brought up to date + sourced (2026-06-05). Applied the Hub's
  platform corrections to the EPS schematic: D1 PESD5V0S1UL -> PESD5V0S1BA (SOD-323,
  C5261083); BOOT/RESET buttons SW1/SW2 Panasonic_EVQPUJ_EVQPUA -> TS-1088-AR02016
  (C720477, same cec-vendor:SW_Push symbol, netlist preserved). Sourced 29/35 parts
  with LCSC (INA238AIDGSR C2868250, ESP32-S3-MINI-1-N4R2 C3013941, RJ45 54602
  C2847314, USB-C C2765186, SS34 C8678, LP5907 C80670, TJA1051T/3 C38695, passives
  reused from the Hub). BOM at modules/eps-8pin/bom/. UNSOURCED (6): RS1/RS2 the
  0.5mOhm 2512 shunt (OQ-11 open) + J_IN1/2/J_OUT1/2 Mini-Fit Jr (THT). ERC clean
  (benign lib_symbol_mismatch). The EPS schematic is now HAND-SOURCED -> do not
  regenerate with gen-modules.py (would revert). gen-modules.py STILL emits
  PESD5V0S1UL + Panasonic button + no LCSC -> apply the same fix to PCIe
  (and/or the generator) on their next pass.
- Generic NTC thermistor vendored + Hub board-temp sensor (2026-06-05). Vendored a
  reusable 10k NTC any board can pull: symbol cec-vendor:Thermistor_NTC (real props
  baked: Murata NCP15XH103F03RC / LCSC C77131 / datasheet; default footprint),
  footprint cec-Resistor_SMD:NTC_0402_1005Metric (real Murata 0402 land via
  easyeda2kicad, KiCad-10), 3D lib/3dmodels/Resistor_SMD.3dshapes/NCP15XH103F03RC.step,
  datasheet cached lib/datasheets/NCP15XH103F03RC.pdf. (10k +/-1% @25C, B25/50=3380K.)
  Then ADDED a board-temp sensor to Hub Standard: TH1 (this NTC) high-side from +3V3,
  R25 10k (C25744) to GND, C16 100nF (C1525) node filter -> TEMP_HUB -> ADC1 IO3
  (the last free ADC1 channel); same topology as the 12VHPWR TH1/TH2. ERC clean
  (benign mismatch + the 2 pre-existing off-grid only), netlist + audit verified, all
  sourced; PCB place/route pending GUI. FOLLOW-UP: the 12VHPWR TH1/TH2 are still the
  R_Small placeholder on a generic R_0402 land with NO LCSC/MPN — repoint them to
  cec-vendor:Thermistor_NTC + cec-Resistor_SMD:NTC_0402_1005Metric + C77131 on that
  board's next pass (identical pins, not yet placed on the PCB = clean swap; left to
  that board's session to avoid a concurrent-edit conflict).
- Vendored symbol pinout audit (2026-06-05): every IC/connector symbol's
  pin#->name verified against the manufacturer datasheet (WebSearch + KiCad stock
  library cross-check; TI/NXP/ST PDF hosts 403 in-session) — INA240 D/SOIC-8
  (1=IN-, 2=GND, 3=REF2, 4=NC [tied to GND, datasheet-sanctioned], 5=OUT, 6=V+,
  7=REF1, 8=IN+) confirmed vs datasheet Fig 6-2 AND our SOIC-8 footprint; the
  PW/TSSOP package has a DIFFERENT pinout, so the orderable MPN MUST be the D part
  (INA240A3DR), never the PW — the symbol value is currently package-ambiguous
  "INA240A3" (pin the D suffix + LCSC# at the 12VHPWR BOM pass).
  INA226/228/238 (identical DGS VSSOP-10; the "extends INA226" is valid),
  TJA1051T/3, LP5907MFX (pin4=NC, no BYP), TPS3839DBZ (3-pin: 1=GND,2=RESET,3=VDD),
  TPS2121RUXR (12-pin, OUT on 1+8), USBLC6-2SC6, SN74AHCT1G08, 74LVC1G17,
  SK6812MINI (plain MINI, NOT MINI-E), PESD5V0S1UL, SS14/SB120, ESP32-S3-MINI-1
  (65-pin) / WROOM-1 (41-pin), RJ45 (pin7=RSVD, pin8=DETECT, +SH1/SH2),
  CEC_CONN_12V2x6 (1-6=+12V/7-12=GND/13-16=sideband), USB-C 16P — ALL correct,
  NO mis-wires. Cosmetic-only (no netlist impact; left unfixed to avoid cross-board
  symbol churn): TPS2121 pin10 "ILM"->"ILIM"; ESP32-S3-MINI-1 symbol Footprint prop
  reads "ESP32-S2-MINI-1" (S2/S3 share the land); 74LVC1G17 pin2/4 blank names;
  CEC_CONN_12V2x6 symbol description still says "APPROXIMATE" (the footprint is now
  the locked official Molex part). The physical +12V/GND row assignment on the
  symmetric 12V-2x6 still needs the §2.8 CEM5.1 check before power (unchanged).
- 12VHPWR outline fix (2026-06-05): the official Molex 12V-2x6 footprint shipped the
  connector mouth/latch profile on Edge.Cuts (39 fp_lines) -> KiCad flagged 4x
  "malformed outline (not a closed shape)". Moved to Dwgs.User in
  lib/cec.pretty/CEC_12V2x6_Horizontal.kicad_mod AND in the board's J3/J4 instances
  (3-tab fp_line discriminator so the 4 real board-edge gr_lines were untouched).
  DRC invalid_outline 4->0; pull onto any other 12V-2x6 board via Update-Footprints-
  from-Library.
- Hub Standard BOM fully sourced for JLCPCB assembly (2026-06-05): all 33 lines
  carry an LCSC part written into the schematic symbols (LCSC/MPN/Manufacturer
  props via the bom skill's edit_properties); 15 Basic/Preferred, 18 Extended,
  ~$12.11/board parts. Outputs in hubs/hub-standard/bom/: bom.csv (tracking) +
  hub-standard-BOM-jlcpcb.csv (Comment/Designator/Footprint/LCSC). Every C-number
  re-validated against jlcsearch (no 404s). Part reconciliations: U6 1G34->1G08
  (JLCPCB stock), U2 -> TJA1051T/3 (as-drawn; see transceiver divergence above),
  D2-D5 UL->BA (SOD-323), D1 SB120->SS14, SW1/2 EVQ->TS-1088 (footprint pulled via
  easyeda2kicad C720477, upgraded to KiCad-10 format + 3D model vendored), R3/R4
  60->60.4. CPL + gerbers still pending the GUI PCB finish (Update-from-Schematic
  to pull U6/R14/C14 + the TS-1088 land, place/route, pour). New open follow-ups:
  (a) PESD UL->BA correction also applies to the EPS/PCIe module
  schematics (still name PESD5V0S1UL "in SOD-323") — fix on their sourcing pass
  (12VHPWR-Std DONE 2026-06-06, see that module's BOM-sourcing note below);
  (b) RESOLVED 2026-06-05 — the transceiver lock is now classical TJA1051T/3
   platform-wide (spec §3.1 v3.5) AND propagated: Hub Standard + all 6 module
   schematics + gen-modules.py now read TJA1051T/3 (C38695), ERC clean each;
   Hub Pro/12VHPWR Pro have no transceiver yet so inherit it when built out;
  (c) DONE 2026-06-05 — J2-J5 RJ45 now carries the authoritative Kinghelm KH-RJ45-58-8P8C (C2683360) footprint, origin-aligned to the routed land (C86580 was a dual-port jack, rejected; see action #2);
  (d) re-check C1 4700uF (~385) and U4 TPS3839K33 (~120) stock before any volume run.
- Hub Standard netclass-pattern fix (2026-06-04): the Power/CAN/USB netclass
  patterns in .kicad_pro lacked the root-sheet "/" prefix, so /5VSB_RAW,
  /+5V_HOLD, /USB_VBUS, /CAN_H, /CAN_L, /USB_DP, /USB_DM all silently fell into
  Default and the .kicad_dru Power-min-width + USB diff-pair rules never fired
  (DRC read clean over a 0.4mm trunk). Added slash-prefixed patterns (kept the
  bare forms). DRC now correctly flags the under-width power traces. Also renamed
  a duplicate FID3 -> FID2 (two FID3, no FID2) and broadened the .gitignore
  analysis/ entry to catch per-board kicad-happy caches.
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
  TJA1051T/3 VCC/VIO bypass — the module U2 value is now TJA1051T/3 (C38695) per
  the v3.5 transceiver lock); DETECT R1 set to the resolved CAN-only 2.2k code
  (OQ-6); ESP corrected to a real MINI-1 SKU (N4R2 — N16R2 was fictitious);
  D1/R7 picked up; and the per-cable IN/OUT interposer pitch widened to 100 mm so
  adjacent cables no longer merge SENSE nets. EPS verified: static audit clean,
  ERC clean apart from the by-design GPIO0 isolated-label and the known generator
  lib_symbol_mismatch noise (ERC is skipped for DRAFT boards anyway).
- Schematic generator now ASSIGNS footprints (gen-modules.py footprint_for +
  cec_sch footprints arg, 2026-06-04) so the modules are BOM-complete and
  round-trip with "Update PCB from Schematic". Shunt land = honest 2-pad
  R_2512 (Kelvin taps drawn in copper at layout, §6.8) — NOT the 4-terminal
  WSK2512. Caps map 0402/0603/0805 by value.
- Flash/debug front end added to ALL generated modules (2026-06-04, gen-modules
  BASE_PARTS), mirroring the 24-pin so every module is flashable: USB-C (J5, ESP
  native USB on pins 24 D+ / 23 D-), VBUS->+5VSB ORing Schottky D2 (SS34) + 10uF
  bulk C9, CC1/CC2 5.1k pulldowns R8/R9, BOOT button SW1 (GPIO0), RESET button
  SW2 (EN). The GPIO0 isolated-label ERC warning is gone now that SW1 connects
  it. Module fp-lib-tables completed (all cec-* footprint libs + cec-MountingHole)
  so footprint links resolve in ERC and the GUI.
- Interposer-module PCB floorplans (2026-06-04, scripts/gen-module-pcb.py — the
  EPS-only gen-eps-pcb.py was generalized; parametric in cable count N). ONE-SHOT
  bootstrap: once a .kicad_pcb is opened/edited in the GUI it is hand-maintained
  (like the 24-pin); do NOT re-run the generator over GUI work. Generated for EPS
  (2 cables, ~110x66 mm), PCIe-2port (2 cables, ~110x66 mm) and PCIe-3port (3
  cables, ~137x66 mm); plus the 12VHPWR Standard (analog-pin kind, NOT cable):
  a ~58x80 mm board (v3.4: FANNED OUT from the earlier slim 44x92 stagger) — 12V-2x6
  power path TOP->BOTTOM down the centre-left (J3 MALE header IN top-centre, 6 FANNED
  per-pin lanes, J4 captive-pigtail OUT bottom-centre), ESP + CAN/LDO + flash +
  RJ-45/USB-C on the RIGHT, 3 M3 corner mounts (TL/TR/BL — the RJ-45 jack body fills
  the bottom-right corner; the 3 through-hole connectors anchor that side). The PLUG
  connectors OVERHANG their edge so a cable seats without the board fouling the plug
  overmold while the solder pads stay on-board: J3's right-angle shroud/mouth
  (~9.5mm deep, local -y) overhangs the TOP edge ~3mm (12V pads ~6.5mm in); J1
  (RJ-45) and J5 (USB-C) overhang the RIGHT edge. J4 (OUT) is ROT 180 (mouth out the
  bottom edge = correct OUT orientation, mirrors J3); the +12V LO nets are remapped
  to the 180-reversed pins (J4 pin 6-j, interchangeable — all common to the GPU 12V
  plane, current already measured at each shunt) so the lanes still DON'T cross.
  (Corrected 2026-06-05: the earlier "J4 NOT 180" was wrong — an OUT connector
  should face out its edge; the remap keeps lanes clean.) Soldered pigtail.
  Added the CEC_CONN_12V2x6 symbol; the CEC_12V2x6_Horizontal footprint is now the
  OFFICIAL Molex 219116 / 2191161161 part (LOCKED 2026-06-05, see §2.8 above — real
  pinout 1-6=+12V/7-12=GND/13-16=signal, ~1.5mm gaps; pick it up on the board via
  Update-Footprints-from-Library, J3 rot 180 / J4 rot 0). FAN-OUT: J3/J4 keep the connector's fixed 3mm pin pitch
  (centered); the six +12V lanes splay symmetrically to a ~6mm SENSE pitch so each
  lane gets its OWN column with room for its in-line shunt -> RC input filter
  (RFH/RFL 10ohm + CF 470n) -> INA240 (rot90, 4.4mm wide fits 6mm) -> bypass
  C10-C15, stacked straight down (short in-column Kelvin, NO staggering), then fan
  back in to J4. Symmetric fan = equal-length lane pairs (length-match the straight
  run in the GUI if the inner/outer spread matters; the 1mohm shunt + contact R
  dominate). The per-lane sense passives (RFH/RFL/CF + C10-15) are PLACED by the
  generator now; the control-side decoupling (C1-C8, R1/R2/R7, D1) still comes via
  Update-from-Schematic. High-current routing PLAN
  is documented in modules/12vhpwr-standard/12vhpwr-routing-plan.png
  (scripts/gen-hpwr-routing-plan.py, ENRICHED v3.4): a to-placement top-down of the
  six equal-length lanes, the four-wire Kelvin detail + the INA RC filter, the
  4-layer stackup, and explicit WIDTH/VIA/STITCH tables — 12V lane 2.5mm on F.Cu +
  2.5mm mirrored on B.Cu paralleled (~13A @ <10C, IPC-2221 2oz); current-carrying
  vias 0.5mm drill / 0.9mm pad (~2A @10C), stitch F<->B ~5mm down each lane + a
  field of 5-6 per shunt terminal + 3-6 per J3/J4 power pin; GND In1/In2/fill on a
  ~5mm grid; Kelvin pair 0.2-0.25mm tight matched pair over the In1 GND plane,
  sense off the INNER shunt edges, RC filter at the INA. NOTE the plan calls for
  BOTH inner pours = GND on this board (the shared stackup's In2 net hint is 12V, a
  cable-board leftover; the pour net is per-zone in the GUI). The copper itself is
  routed in the GUI (CLAUDE routing boundary). All:
  4-layer, 2oz outer / 1oz inner (hpwr: 12V on both outers, GND both inners; cable
  boards In1=GND, In2=12V).
  N cables inline (PSU-side IN on the top edge, load-side OUT on the bottom — 12V
  flows top->bottom through each cable's 2-pad R_2512 shunt + INA238), the cables
  INSET so the four corner M3 mounts (MountingHole_3.2mm_M3_Pad_Via) stay clear of
  the connectors; the control/power core (ESP, CAN, LDO) + flash front end (USB-C,
  BOOT/RESET, ORing diode + CC) + RJ-45 fill the right. The USB-C (J5) and RJ-45
  (J1) are rotated 90 so they mate OUTWARD on the right edge; the generator bakes
  the footprint rotation into the pad angles (KiCad convention) so kicad-cli's
  headless DRC does not report false within-footprint pad shorts on rotated parts.
  CEC copper logo on the back. The generator now also writes each part's VALUE
  onto F.SilkS (v3.4): footprints default the Value to the footprint name on the
  non-plotted F.Fab layer, so values never showed on the board — place() rewrites
  the Value property to the netlist value and moves it to F.SilkS (Reference stays
  on silk; mounts/logo pass val=None and keep their Fab default). This adds silk-
  overlap warnings on the dense clusters (a GUI silk-refinement task) but makes the
  values readable. DRC verified after the v3.4 12VHPWR re-tighten: 0 structural hits
  (0 copper shorts / clearance / courtyard / copper-edge); the remaining DRC is silk
  (values-on-silk + tight placement) + the known benign lib_footprint_mismatch. The
  cable boards (EPS/PCIe) are unchanged in placement and keep their ~1 courtyard
  touch. Added the Mini-Fit Jr 2x4 footprint to lib/vendor/Connector_Molex.pretty
  and tightened the ESP NoAntKeepout courtyard (45x35 -> 16x21 mm; antenna keep-out
  dropped — wired-only modules). Next in GUI: pull the discrete passives via
  Update-from-Schematic (incl. the 12VHPWR INA input-filter RFH/RFL/CF + sideband
  taps R10-R13), then place/route + pour.
- §6.4 shunt values applied across the generator/boards.
- 12VHPWR routing netclasses LOADED into modules/12vhpwr-standard/*.kicad_pro
  (2026-06-04) so the GUI auto-applies width + via per net while routing: Power12V
  (track 2.5mm, via 0.9/0.5mm, clr 0.25 — pattern /SENSEP* = the six 12V lanes),
  Sense (0.25mm, via 0.6/0.3 — /INPP* /INNP* /ISENSEP* /VRAIL_DIV), GND (0.5mm, via
  0.9/0.5), Power (0.5mm, via 0.8/0.4 — +3V3/+5VSB/VBUS), CAN, USB (diff), Default.
  Predefined track-width (0.25/0.3/0.5/1.0/2.5) and via (0.6/0.3, 0.9/0.5) menus
  added to design_settings. The thin Kelvin TAP shares the 12V net (SENSE*_HI), so
  it can't be netclass-thin — draw that short stub by hand with the 0.25mm preset;
  the INP/INN nets after the filter Rf ARE separate and auto-take the Sense class.
  Stackup wording corrected: 12V/GND/GND/12V means the GND pair is sandwiched by
  the 12V outers (NOT 12V by GND) — each 12V lane just runs directly against a GND
  plane (small return loop). .kicad_pro is GUI-owned; do not regenerate it.
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

- **Judge routed candidates THROUGH the tiered pipeline, not by eyeballing the
  deterministic verdict.** For any route-to-clean / route-quality / gate decision, spawn a
  manager (Sonnet) sub-agent to judge + a re-verify escalator pass — see the rule under
  "Sub-agent routing pass — GO-AHEAD". A bare deterministic route is only for a quick smoke.
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

### The constraint loop's human-ratification boundary — SET IN STONE (2026-06-07)

The constraint-aware **place → route → check** loop (`scripts/cec_loop.py`: `cec_place` +
`cec_fr` + `cec_hc` + `cec_constraints`) is DESIGNED to run itself to a wall and then ESCALATE
TO THE HUMAN. When the only remaining fix is a **constraint-level or design-level change** —
loosen a ratified target, change the stackup, add a plane/pour, alter a footprint, relax a
locked decision — the loop does NOT silently change a ratified constraint or assume a design
decision. Reaching that wall is the loop **WORKING AS INTENDED**, not a failure (this is the
`discover → ratify → enforce` migration's top rung: the human is the ratifier tier).

At the wall the loop has **two levers**, and it should prefer (1) before asking for (2):
1. **Go back to the top — regenerate a PLACEMENT CANDIDATE.** Vary the placement (rotation /
   tighten target / seed / strategy) and re-run place→route→check to try to clear the wall
   WITHOUT any design change. A different candidate often fixes what looked like a constraint
   problem (e.g. a sense IC boxed against its shunt so its own power/GND can't escape).
2. **Surface the design/constraint decision to the HUMAN, who ratifies it.** A ratified change
   is **BOARD-SPECIFIC by default** — it applies to the one board, NOT generalized to the
   platform unless the human/spec says so. (Worked example, 2026-06-07: the EPS tight-Kelvin
   placement strands the INA238's own +3V3/GND; the human ratified *loosen the EPS Kelvin
   target a hair* — recorded BOARD-SPECIFIC in `cec_loop.BOARD_PARAMS`, not as a platform
   default; the alternative, lever 1, is to regenerate a looser placement candidate.)

Never relax a ratified threshold or make a stackup/footprint/locked-decision change to "get a
board to pass" without this escalation. Lever-1 candidate regeneration is automatic; lever-2 is
the human's call and is logged with its board scope.

### Sub-agent routing pass (real copper) — GO-AHEAD (2026-06-06)

**DEFAULT TO THE FULL TIERED PIPELINE FOR ANY ROUTE-QUALITY / ROUTE-TO-CLEAN / GATE
DECISION — do NOT just read `cec_router`'s deterministic verdict and hand-analyse it
(rule added 2026-06-06).** The deterministic plane GENERATES + SCORES; the LLM tiers
JUDGE + FIX, and skipping them hides real problems. Whenever you check or iterate a
routed candidate — route-to-clean, a pour / placement / netclass / rule change, "is this
board better?", or judging gates / DRC / snags — drive it THROUGH the control plane:
spawn a **manager** (Sonnet) sub-agent to read the candidate's metrics + gate failures +
DRC-type breakdown and return `accept` / `repair` / `escalate` with a root-caused
recommendation, then act as the **escalator** (apply the edit via `apply_edit` or a board
change, re-route, re-verify). This is the difference between catching and missing a
safety regression: a 12V copper pour that silently broke the `SENSEC2_LO` **Kelvin HARD
GATE** (cable-2 sense stranded on an inner layer) was only caught once it went through the
manager — a bare deterministic `drc=58` reading would have shipped it. `cec_router` already
ships the `make_subagent_policy()` hooks for exactly this; use them. A deterministic-only
route is acceptable ONLY for a quick generate / smoke test, NEVER for judging a board's
quality or a gate's status.

Generating routing CANDIDATES as real copper is sanctioned, and it stays **sub-agent
generation** — the orchestrator builds/maintains the toolkit and spawns the passes; it
does not hand-route. `pcbnew` (the real KiCad 10 Python engine) is available in this
environment and can do what `kicad-cli` cannot: create real `(segment)`/`(via)` copper
and FILL pours with the real `ZONE_FILLER`, verified by the real DRC + connectivity.

The candidate pipeline is a loop of sub-agent passes that feed each other:

1. **Placement / footprint pass** → the floorplan (`cec_pcb.auto_cluster` / `place_offsets`).
2. **Routing game-plan pass** → per-net-class layers / widths / vias / waypoints (the plan
   drawn by `cec_pcb.guides` + `routing_plan_png`).
3. **Routing pass (`scripts/cec_route.py`)** → realizes the game-plan as REAL copper on a
   COPY of the board (`Router`: `track` / `via` / `zone` / `fill` / `verify`), routes the
   deterministic nets clean (12V pours filled + split at the shunt, GND plane + stitching,
   Kelvin stubs, the USB diff pair, CAN, short point-to-point), and attempts the dense
   control→sense spine. It VERIFIES with the real engine and then **reports the snags +
   the precise changes the upstream passes must make** — it does not silently edit
   placement/footprints/the plan itself. Feedback is split:
   - **→ footprint/placement pass:** move/rotate a part, widen a band, fix a pad escape.
   - **→ game-plan pass:** change a net's layer/lane/width, add vias, re-order.
4. The orchestrator acts on the feedback (re-spawn the placement or game-plan pass), then
   re-runs the routing pass. The honest expectation: deterministic nets route clean
   headlessly; the dense crossing spine may need a placement/plan change, an external
   autorouter (Freerouting via DSN — `java` is present, the jar is not), or the GUI.

Rules for the routing pass: route a COPY (never the committed floorplan in the same step),
verify with the real DRC/fill engine before claiming a net routed, and keep the snag→change
feedback specific (net names, refs, deltas, coordinates). The committed floorplan is updated
only after its placement/plan actually changes, via the normal placement/plan passes.

## What Claude should NOT do

- Do not HAND-edit PCB routing geometry — do not poke `(segment)` / `(via)` track
  s-expr or copper-zone fill into a `.kicad_pcb` by text. That hand-editing boundary
  stays. **EXCEPTION (GO-AHEAD, 2026-06-06):** real copper MAY now be generated
  PROGRAMMATICALLY through the real KiCad engine via the pcbnew-backed routing toolkit
  `scripts/cec_route.py`, run as a **sub-agent routing pass** (see "Sub-agent routing
  pass" under "What Claude should do"). That path emits genuine tracks/vias and FILLS
  pours with the real `ZONE_FILLER` (which `kicad-cli` cannot do), and verifies with
  the real DRC + connectivity engine — so it is sanctioned where hand-poking is not.
  Fine layout geometry the toolkit doesn't cover (e.g. hand-tuning the §6.8 Kelvin
  sense meander) still belongs in the GUI. Component PLACEMENT is allowed and expected.
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
- RJ-45 shielding (§2.1 / OQ-37): spec LOCKS FTP. Hub Standard (J2-J5), 12VHPWR
  Standard AND EPS now use the FTP footprint (cec:RJ45_FTP_Shielded_Horizontal,
  Kinghelm KH-RJ45-58-8P8C / C2683360) with SH1/SH2 -> GND; before fab verify the
  shield-tab + peg geometry. The 24-pin + the two PCIe SKUs still carry the unshielded
  54602 (compatible — single-end shield at the Hub) and pick up the FTP jack on their
  next gen-modules.py regen.
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
