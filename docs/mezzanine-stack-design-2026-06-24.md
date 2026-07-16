# Mezzanine stack: Hub-on-24-pin integrated unit — design draft (2026-06-24)

PROPOSAL: an OPTIONAL configuration where the Hub Standard physically stacks on the 24-pin ATX module via a
vertical board-to-board connector, sharing grounds through metal mount standoffs. Eliminates the inter-board
RJ-45 cable + the 2-pin 5VSB cable; yields a compact integrated "Hub+24-pin" unit. Same LOGICAL interface
(CAN / DETECT / RS-485 / +5VSB) over a new optional PHY. Target: the next 24-pin rev (rev3) + a Hub rev.

## 1. Configuration
- 24-pin module = BASE (anchored by the ATX Mini-Fit headers + cable). Hub stacks ON TOP, component-side up.
- Inter-board gap = the connector stack height = the standoff length (LOCKED TOGETHER). Target **8mm**.
- The 24-pin's TALL parts (Mini-Fit Jr headers, RJ-45, USB-C, ~13mm) must sit at the EDGE/overhang region,
  clear of the Hub footprint, so the 8mm gap only clears the low interior (INA/passives ~2mm) + the connector.
  (Tonight's edge-overhang work already pushes those connectors to the edges -- this reuses it.)

## 2. The connector
- **2x8 (16-pin) dual-row 2.00mm board-to-board pair, 8mm mated stack height, >=3A/pin, keyed.**
  24-pin carries the MALE header (pins up); Hub carries the FEMALE socket (on its bottom side).
- Candidate families: generic 2.0mm dual-row header+socket (cheap, LCSC-stocked) or a proper board-to-board
  (Wurth WR-BHD 2.0mm / Amphenol / Molex SlimStack) for keying+retention. Source the exact LCSC C-number at BOM.
- **MIRROR GOTCHA (the #1 mezzanine error):** the Hub is FLIPPED to stack, so its socket footprint pinout is
  the X-MIRROR of the 24-pin's header. Pin 1 (header) must land on the socket contact it physically mates with
  after the flip. Draw the Hub footprint mirrored and net-check the mated pairs explicitly.
- Mechanical load goes through the STANDOFFS, not the connector (connector = signals only).

## 3. Pinout (2x8, GND-interspersed for SI + current)

> **CORRECTED 2026-07-03 (beta splice, B4/K1 gate).** This table as originally drafted
> (2026-06-24, below the strikethrough) was never actually implemented — the real build,
> on BOTH sides of the mated pair, used a different pin assignment from the start (one
> off-by-one GND pin per flank, absorbed into a 3rd +5V_SYS pin at position 3 instead of
> 15). See the reconciliation table in `docs/standard-tier-review/beta-splices/
> atx-24pin.md` §J6 for the full pin-by-pin evidence trail. The table below is now the
> AS-BUILT, single source of truth — matches `modules/atx-24pin-rev3/24pin-module.kicad_sch`
> (J6) and `hubs/hub-rev2/hub-rev2.kicad_sch` (J_MEZZ) exactly, verified via both schematics'
> exported netlists.

```
 Pin  Signal      Pin  Signal
  1   +5V_SYS      2   +5V_SYS    <- bulk +5V_SYS (24-pin sources it), 3 pins total
  3   +5V_SYS      4   GND
  5   CAN_H        6   CAN_L      <- diff pair, single-GND-flanked (4 / 7)
  7   GND          8   STREAM_P
  9   STREAM_N    10   GND        <- RS-485 (Pro); populate now for forward-compat
 11   DETECT      12   GND        <- the 2.2k module-ID, read on the Hub pull-up
 13   RSVD        14   GND
 15   GND         16   GND
```
Totals: +5V_SYS x3 (1,2,3), GND x7 (4,7,10,12,14,15,16) for return + the shared-ground + guards,
CAN_H/L, STREAM_P/N, DETECT, RSVD. +5V_SYS ~2.5A over 3 paralleled pins (~9A capacity) = comfortable.

<details><summary>Superseded draft (2026-06-24, never matched either built schematic — kept for provenance)</summary>

```
 Pin  Signal      Pin  Signal
  1   +5VSB        2   +5VSB      <- bulk 5VSB (24-pin sources it), 3 pins total
  3   GND          4   GND
  5   CAN_H        6   CAN_L      <- diff pair, GND-flanked (3,4 / 7,8)
  7   GND          8   GND
  9   STREAM_P    10   STREAM_N   <- RS-485 (Pro); populate now for forward-compat
 11   GND         12   GND
 13   DETECT      14   RSVD       <- the 2.2k module-ID, read on the Hub pull-up
 15   +5VSB       16   GND
```
Totals: +5VSB x3 (1,2,15), GND x7 (3,4,7,8,11,12,16) for return + the shared-ground + guards, CAN_H/L,
STREAM_P/N, DETECT, RSVD. +5VSB ~2.5A over 3 paralleled pins (~9A capacity) = comfortable.

</details>

## 4. Shared-ground-via-mounts + the alignment CONTRACT
- The Hub already has 4 corner M3 mounts ALL ON GND (rect 86 x 61.7mm). The 24-pin rev2 has NO mounts -> ADD
  4 (>=3) M3 mounts with GND rings, aligned to the Hub's.
- **8mm metal M3 standoffs** bond GND plane-to-plane at the 4 corners (+ the connector's 7 GND pins) = a
  low-impedance bond for CAN/RS-485 SI + the 5VSB return, AND the mechanical stack height.
- **Alignment contract (both rev layouts MUST honor):** a shared frame = {the mezzanine connector reference
  (x,y,rot) + the 4-mount rectangle}. Constraint: the rectangle must fit within BOTH outlines (24-pin 83x79,
  Hub 98x74 -> the 86mm Hub pattern is TOO WIDE for the 83mm 24-pin; shrink the shared rect to <=~76 x ~60mm)
  AND the Hub footprint must clear the 24-pin's edge connectors. Recommended target: 4 mounts on a ~74 x 58mm
  rectangle, connector centered in the overlap. Finalize exact coords during the rev3 + Hub-rev layout.

## 5. Make it an OPTION (population variants, one PCB each)
- 24-pin: mezzanine header pins -> the SAME nets as J1 (RJ-45 link: +5VSB/CAN1_P/CAN1_N/DETECT/GND/RSVD) +
  J2 (+5VSB/GND). Stacked build = populate mezzanine, DNP J1+J2. Cabled build = populate J1+J2, DNP mezzanine.
- Hub: mezzanine socket -> ONE port's nets (a dedicated "port 0", e.g., reuse J2's CAN_H/CAN_L/DETECT1/+5VSB/GND)
  + the +5VSB power-in. The other 3 RJ-45 ports stay live for additional modules. DETECT works identically.
- Forward-compat: a Pro 24-pin would populate STREAM_P/N (RS-485) on pins 9/10 -- already in the pinout.

## 6. Implementation steps (next rev)
1. Vendor a mezzanine symbol + 2 footprints (MALE header on 24-pin, MIRRORED FEMALE socket on Hub) in lib/.
2. 24-pin rev3 schematic: add the header, wire pins 1-16 per the pinout to the link+power nets; add 4 M3 GND mounts.
3. Hub rev schematic: add the (mirrored) socket on B.Cu, wire to a dedicated port-0 + power-in nets.
4. PCB both: place connector + mounts on the shared alignment frame; keep the Hub footprint clear of the
   24-pin's edge connectors; verify the 8mm gap clears all facing components (the gating mechanical check).
5. BOM: 8mm M3 metal standoffs + screws; source the exact 2.0mm 2x8 board-to-board pair.
6. Population variants: mezzanine XOR (RJ-45 + JST).

## 7. Spec-revision proposal (new OQ)
The module<->Hub link is LOCKED to RJ-45 8P8C. This adds an OPTIONAL board-to-board PHY for the integrated
stacked Hub+24-pin assembly, carrying the IDENTICAL logical interface. Propose as a new spec section + OQ:
"OQ-xx: integrated mezzanine stack option (Hub-on-24-pin); RJ-45 remains the default/cabled PHY."

## 8. Gating checks before committing
- Component-height vs 8mm gap (confirm the Hub footprint clears the 24-pin's edge connectors).
- The mirrored-socket mated-pair net check (do NOT skip).
- +5VSB current + GND return across the connector (pin sizing) -- 3+7 looks comfortable.
- EMC: stacked-board loop area -- the 4-corner GND bond + 7 connector GNDs is the mitigation; do an EMC pass.
