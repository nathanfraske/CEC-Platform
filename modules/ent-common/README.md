# ent-common — shared ESP32-P4 + 100BASE-T1 module reference block

Board-program scope: **designed once, instantiated ×4** by the enterprise (ENT)
builds of the four module families (`atx-24pin`, `eps-8pin`, `pcie-8pin-2port` /
`pcie-8pin-3port`, `12vhpwr-standard`/`12vhpwr-pro`). This directory does NOT
define a board of its own — it defines the sub-circuit BLOCK every ENT module
family's own schematic instantiates (today, by copying/adapting the block —
KiCad hierarchical sheets are the natural home for this once the T4 schematic-
composition engine lands, see `docs/schematic-quality-charter.md`; this pass
captures the block's netlist truth with today's primitives, per that doc's own
guidance: "capture with today's primitives, it regenerates later").

## What the block is

The tier-agnostic ENT common backbone required by
`docs/enterprise-requirements/module-requirements-common.md`
(REQ-MOD-COMMON-001, -003, -010..-013, -053) and spelled out in
`docs/enterprise-requirements/spec-sheets/module-ent-spec-sheets.md` §0:

- **RJ-45 8P8C FTP** module-to-Hub link (platform universal interface,
  `cec:CEC_RJ45_8P8C_FTP`), SH1/SH2 → GND.
- **ESP32-P4** (radio-free, uniform ENT MCU, `cec-ent-mcu:ESP32-P4`) +
  external QSPI flash (`cec-ent-power:W25Q256JVFIQ`, reused off the Hub's own
  boot-flash part per the task brief — see FLAGS, right-sizing is open) + a
  main XTAL + a first-pass decoupling field.
- **USB-C flash/debug front end** — reused VERBATIM from the platform pattern
  (`modules/eps-8pin`): ORing Schottky (D3, SS34) into the raw `+5VSB` node,
  CC1/CC2 5.1 kΩ pulldowns, BOOT (GPIO0) / RESET (CHIP_PU) buttons.
- **TPS26621 60 V auto-retry eFuse** (U2) directly between RJ-45 pin 1 and the
  LP5907-class 3V3 LDO's input — REQ-MOD-COMMON-053: "pin-1 5VSB enters HERE."
  A diode cannot protect a power INPUT (fault current flows the normal
  direction); the eFuse is the only element that can. USB VBUS ORs into the
  SAME pre-eFuse node, so a bench USB supply gets the identical OVP protection
  as the RJ-45 feed.
- **TJA1051T/3 CAN transceiver** (U4) on pins 3/6, classical 500 kbps, no
  module-side termination (unchanged locked platform behavior).
- **DETECT (pin 8), ENT class**: NEW series resistor (R7, survey 11 §(c)) →
  node carrying the 10 kΩ ENT code resistor (R8, the locked CAN+100BASE-T1
  class, §2.3) + a low-cap ESD clamp (D1) + the platform poke-and-ack tap
  (R9, 100 kΩ → an MCU ADC/GPIO pin) — REQ-MOD-COMMON-010/053.
- **Pin 7 — SYNC/FREEZE + heartbeat responder** (NEW, REQ-MOD-COMMON-013 /
  REQ-HUB-COMMON-112/114): series R (R10) → a low-capacitance ESD clamp (D2,
  same part family as DETECT's) → an MCU GPIO chosen for hardware timer/
  output-compare capability. This supersedes the OLDER "1 MΩ bleed-R + SMAJ58A
  TVS" treatment for pin 7 that applied when it was still just a reserved
  spare (see `hub-ent-bom-detailed.md` §6a's own reconciliation note) — pin 7
  is now a DRIVEN line (both directions: the Hub drives the sync edge /
  challenge, the module drives the heartbeat response), so the network must
  preserve a fast, low-capacitance edge, not just bleed a floating node.
- **100BASE-T1 module link** on pins 4/5 (REQ-MOD-COMMON-003, survey 10/11):
  RJ-45 → common-mode choke (`cec-ent-net:ACT1210L-201-2P-TL00`) → per-line
  ≥100 V AC-coupling capacitor (the actual DC-fault-blocking element) →
  **DP83TC814S-Q1** PHY (`cec-ent-net:DP83TC814S-Q1`) MDI pins (TRD_P/TRD_M) →
  PHY-side ESD (`cec-ent-net:PESD2ETH100-T`, ≥100 V trigger, inert through the
  accepted 57 V mis-plug fault) → RMII to the ESP32-P4.

## Per-family instantiation contract

Each ENT module family's own schematic is expected to bring in this block
(today: adapt/copy the netlist pattern; later: a real hierarchical sheet) and
wire ONLY the family-specific sensing bus on the MCU side. The block's
boundary is:

**Inputs the block needs from the family sheet (hierarchical-pin interface,
MCU-side):**

| Signal | Direction | Purpose |
|---|---|---|
| I²C SDA/SCL, or the family's analog ADC inputs | MCU → sensing | Whatever bus the family's INA228/INA238/INA240/ADS131M08 sensing chain uses is NOT part of this block — it lives entirely on free ESP32-P4 GPIO/ADC pins, exactly like the consumer-tier pattern (`gen-modules.py`'s per-family sensing build). This block only reserves the GPIOs it uses for itself (see the GP{} table in `gen_p4_t1_block.py`) and leaves the rest free. |
| Firmware event/telemetry hooks | MCU-internal | The §6.10 acquisition/FREEZE model, the pin-7 heartbeat's device-key/nonce compute, and the DETECT poke-and-ack liveness check are firmware concerns riding on this block's GPIOs — not additional hardware. |

**Outputs the block presents to the family sheet / to the Hub (RJ-45 pins):**

| RJ-45 pin | Net (this block) | Family-visible behavior |
|---|---|---|
| 1 (VCC/+5VSB) | `+5VSB` → eFuse → `+5VSB_FUSED` | Every family's 3V3 rail (and CAN transceiver 5V) comes from `+5VSB_FUSED`, never the raw jack pin. |
| 2 (GND) + SH1/SH2 | `GND` | Common return + shield ground. |
| 3 / 6 (CAN1_H/L) | `CAN_H` / `CAN_L` | Classical CAN, unchanged from consumer tier. |
| 4 / 5 (STREAM_P/N) | `T1_A_RAW` / `T1_B_RAW` → CMC → PHY | ENT-only: 100BASE-T1, not RS-485 (REQ-MOD-COMMON-003). |
| 7 (RSVD → SYNC/FREEZE) | `SYNC7_RAW` → R10 → `SYNC7` | ENT-only: driven sync/heartbeat line, NOT the consumer "reserved spare." |
| 8 (DETECT) | `DETECT_RAW` → R7 → `DETECT_A` | 10 kΩ ENT class (was 2.2/4.7 kΩ on consumer/Pro), recomputed for the new series R (firmware-recalibrated per survey 11 §(c)). |

A family that instantiates this block therefore ONLY needs to add: its own
in-path sensing (shunts + INA-class monitors or the fast-ADC front end),
family-specific connectors (24-pin JST, EPS/PCIe Mini-Fit Jr 2×4, or the
12V-2x6), and any family-specific mezzanine/sideband signals — never a second
copy of the RJ-45/CAN/DETECT/pin-7/T1/eFuse/flash/USB front end.

## Files

- `gen_p4_t1_block.py` — the generator (uses `scripts/cec_sch.py`'s shared
  emit helpers, same idiom as `scripts/gen-modules.py`; does not modify that
  shared script). Run: `python3 modules/ent-common/gen_p4_t1_block.py`.
- `p4-t1-block.kicad_sch` — the block, captured flat (wire-stub + net-label
  primitives; the T4 composition/layout engine is not yet integrated — see
  `docs/schematic-quality-charter.md`).
- `p4-t1-block.kicad_pro`, `sym-lib-table`, `fp-lib-table` — minimal project
  scaffolding (no netclasses/DRU yet; this block is schematic-only, no PCB).
- `ent-common-local.kicad_sym` — ONE project-local stopgap symbol
  (`Crystal_Small`, a generic 2-pin crystal placeholder; no MPN chosen yet),
  mirroring the `hub-enterprise/lib-local.kicad_sym` convention for parts not
  yet promoted to a shared `cec-ent-*` library.
- `check_p4_t1_block.py` — netlist assertion harness (eFuse-in-series, DETECT
  chain, pin-7 chain, T1 MDI chain, CAN H/L, RMII pin-map sanity vs the
  vendored DP83TC814S-Q1 symbol's TI-datasheet-derived pin names). Run:
  `python3 modules/ent-common/check_p4_t1_block.py`.

## Verification status (2026-07-03)

- `kicad-cli sch erc`: 117 violations, but EVERY ONE falls into an
  already-documented-benign class (see `check_p4_t1_block.py`'s
  `KNOWN_BENIGN` table): 51 `lib_symbol_mismatch` (generator re-serialization
  cosmetic noise, repo-wide known class), 59 `pin_to_pin` + 7 `pin_not_driven`
  (all traced to the vendored ESP32-P4 / DP83TC814S-Q1 / ACT1210L /
  PESD2ETH100-T symbols typing every pin `Unspecified` — the exact class the
  schematic-quality-charter's T2 `cec_sym_audit.py` pass already found and
  flagged across the `cec-ent-*` libraries; this is a symbol-library gap, not
  a wiring defect in this block, and fixing it is T2's `--fix` mode, out of
  this task's scope). **Zero unexplained/untriaged ERC classes.**
- `check_p4_t1_block.py`: all netlist assertions pass (eFuse in series,
  DETECT chain, pin-7 chain, T1 MDI chain, CAN H/L, 12/12 RMII pin-name
  cross-checks against the vendored PHY symbol).
- `scripts/cec_sch_render.py p4-t1-block.kicad_sch --out build/ent-common-render
  --tiles 2x3`: renders (see the render substrate note in the charter); tile
  count reported by the render run.

## FLAGS — open items, not silently resolved

1. **RMII pin assignment on the ESP32-P4 is a PLACEHOLDER.** The vendored
   `cec-ent-mcu:ESP32-P4` symbol carries no alternate-function/IO_MUX
   annotation — every pin is named generically `GPIOn`. Which physical pins
   actually serve the EMAC/RMII peripheral (and whether the 50 MHz REF_CLK
   needs one specific dedicated pin, vs. any GPIO via the matrix) is **NOT
   confirmed against Espressif's ESP32-P4 TRM in this session**. `GP{}` in
   `gen_p4_t1_block.py` assigns GPIO1–16 to CAN/DETECT/pin-7/MDIO/RMII purely
   to produce a wireable, ERC-clean reference block — re-pin at schematic
   capture once the real IO_MUX table is in hand.
2. **`DP83TC814S-Q1` pin 28 ("TX_CLK") is wired as the RMII REF_CLK — UNCONFIRMED.**
   Survey 10/11 and the vendored symbol's own datasheet citation (TI SNLS663B
   Table 5-1) do not resolve whether this PHY sources or accepts the 50 MHz
   RMII reference clock on this pin, or whether REF_CLK is a separate net
   entirely. Flagged rather than guessed silently; verify against the PHY
   datasheet's RMII timing/clocking section before layout.
3. **ESP32-P4 power tree is a first-pass simplification.** Every `VDD_*` pin
   (HP_0..3, IO_0/4/5/6, LP, ANA, BAT, LDO, DCDCC, USBPHY, MIPI_DPHY,
   PSRAM_0/1, VDDO_FLASH/PSRAM/3/4, FLASHIO) is tied to one board `+3V3` net;
   `EN_DCDC` is strapped to GND (assumes internal-LDO mode, not
   datasheet-verified); `FB_DCDC` is left unconnected. Espressif's ESP32-P4
   Hardware Design Guidelines (referenced in the task brief, not available in
   this session) should be consulted before board-level capture to confirm
   which rails are truly independent and whether the internal buck
   (EN_DCDC/FB_DCDC/VDD_DCDCC) is actually wanted.
4. **External QSPI flash part is oversized/placeholder.** `U5` is the Hub's
   own `W25Q256JVFIQ` (256 Mbit) reused verbatim per the task brief's own
   suggestion ("W25Q-class from cec-ent-power or the platform flash part") —
   a module almost certainly wants a smaller/cheaper W25Q density; right-size
   at BOM-lock, not resolved here.
5. **Both crystal frequencies are UNVERIFIED placeholders.** `Y1` (P4 main
   XTAL, valued "40MHz") and `Y2` (PHY XTAL, valued "25MHz") are project-local
   stopgap parts (`ent-common-local.kicad_sym:Crystal_Small`, no MPN) with
   frequencies chosen by convention/recollection of typical Espressif/TI
   reference designs, NOT confirmed against either datasheet this session.
6. **TPS26621 application-circuit values (UVLO/OVP/ILIM/dVdT dividers, R1-R6,
   C1) are illustrative placeholders**, not computed from the TI TPS26621
   datasheet's sizing equations — survey 11 itself flags the OVP threshold
   sizing as "a schematic-capture/bench-calibration task," and that applies
   equally to the other three app pins captured here.
7. **AC-coupling cap value/voltage rating for the T1 pair (C20/C21, valued
   "10n") is a placeholder** — survey 11 §(e) explicitly defers the exact
   value to "survey 10's [pin] against the chosen PHY's application note"
   (TI SNLA389A), not resolved in this session.
8. **DETECT/pin-7 series-R values (R7 = 10 kΩ, R10 = 100 Ω) are illustrative,
   not bench-tuned.** Survey 11 §(c) explicitly brackets the DETECT series R
   at "4.7k–20k" pending "schematic-capture/bench-calibration," and the
   pin-7 reconciliation note in `hub-ent-bom-detailed.md` §6a calls its own
   series-R + clamp sizing a "schematic-capture task" so the ≤100 ns sync
   edge and the timed heartbeat edges survive the network — neither value is
   verified against that constraint here.
9. **eFuse SHDN policy (U2 pin 4) is tied high (always-armed)** — no
   MCU-controlled shutdown GPIO is wired, since no REQ defines one yet; flagged
   as a reasonable per-family enhancement point, not a decision made here.
10. **Decoupling field is netlist-equivalent, not pin-by-pin.** The ~10
    bulk/bypass caps on the P4's `+3V3` net approximate Espressif's hardware
    design guideline class counts but are not placed/counted per-VDD-pin;
    that remains a layout-stage task (same scoping note the eps-8pin/12VHPWR
    boards use for their own decoupling fields).
11. **This block has no PCB/layout yet** — it is schematic-only. No
    `.kicad_pcb`, no netclasses/`.kicad_dru`. Per-family PCB instantiation is
    out of this task's scope.
