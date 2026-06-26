# Mezzanine stack: Hub-on-24-pin integrated unit — design draft (2026-06-24)

PROPOSAL: an OPTIONAL configuration where the Hub Standard physically stacks on the 24-pin ATX module via a
vertical board-to-board connector, sharing grounds through metal mount standoffs. Eliminates the inter-board
RJ-45 cable + the 2-pin 5VSB cable; yields a compact integrated "Hub+24-pin" unit. Same LOGICAL interface
(CAN / DETECT / RS-485 / +5VSB) over a new optional PHY. Target: the next 24-pin rev (rev3) + a Hub rev.

## 1. Configuration
- 24-pin module = BASE (anchored by the ATX Mini-Fit headers + cable). Hub stacks ON TOP, component-side up.
- Inter-board gap = the connector stack height = the standoff length (LOCKED TOGETHER). **Target 14mm
  (OWNER DIRECTIVE 2026-06-25: minimum 14mm).** Raised from 8mm so the gap clears the 24-pin's TALL edge
  connectors (J1 RJ-45 ~14mm, J3/J4 ATX Mini-Fit ~10.7mm) EVEN WHERE the Hub footprint overlaps them — the
  gap no longer depends on those connectors sitting purely in the overhang region.
- The 24-pin's TALL parts (Mini-Fit Jr headers, RJ-45, USB-C, ~13-14mm) still want the EDGE/overhang region
  where possible; the 14mm gap then comfortably clears the low interior (INA/passives ~2mm) + the connector.

## 2. The connector
- **2x8 (16-pin) dual-row 2.00mm board-to-board pair, 14mm mated stack height, >=3A/pin, keyed.**
  24-pin carries the MALE header (pins up); Hub carries the FEMALE socket (on its bottom side).
- **14mm STACK-HEIGHT IMPLICATION (owner's 14mm minimum):** a 14mm mated height is TALLER than a generic
  2.0mm pin-header+socket (those top out ~8-11mm). Options at BOM: (a) a board-to-board family that ships a
  14-15mm stack height (Würth WR-BHD / Samtec / Amphenol — defined stack heights, keyed+retained), OR (b) a
  tall-pin 2.0mm header (e.g. 15-16mm pin length) mated into a socket so the boards seat at 14mm. The 2x8
  2.0mm LAND is unchanged; only the part height + the matching standoff length (14mm M3) change. Confirm the
  chosen part's current rating (>=3A on the 3 paralleled +5V_SYS pins) and keying.
- Candidate families: generic 2.0mm dual-row header+socket (cheap, LCSC-stocked) or a proper board-to-board
  (Wurth WR-BHD 2.0mm / Amphenol / Molex SlimStack) for keying+retention. Source the exact LCSC C-number at BOM.
- **MIRROR GOTCHA (the #1 mezzanine error):** the Hub is FLIPPED to stack, so its socket footprint pinout is
  the X-MIRROR of the 24-pin's header. Pin 1 (header) must land on the socket contact it physically mates with
  after the flip. Draw the Hub footprint mirrored and net-check the mated pairs explicitly.
- Mechanical load goes through the STANDOFFS, not the connector (connector = signals only).

## 3. Pinout (2x8, GND-interspersed for SI + current)
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

## 4. Shared-ground-via-mounts + the alignment CONTRACT
- The Hub already has 4 corner M3 mounts ALL ON GND (rect 86 x 61.7mm). The 24-pin rev2 has NO mounts -> ADD
  4 (>=3) M3 mounts with GND rings, aligned to the Hub's.
- **14mm metal M3 standoffs** bond GND plane-to-plane at the 4 corners (+ the connector's 7 GND pins) = a
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
   24-pin's edge connectors; verify the 14mm gap clears all facing components (the gating mechanical check).
5. BOM: 14mm M3 metal standoffs + screws; source the exact 2.0mm 2x8 board-to-board pair.
6. Population variants: mezzanine XOR (RJ-45 + JST).

## 7. Spec-revision proposal (new OQ)
The module<->Hub link is LOCKED to RJ-45 8P8C. This adds an OPTIONAL board-to-board PHY for the integrated
stacked Hub+24-pin assembly, carrying the IDENTICAL logical interface. Propose as a new spec section + OQ:
"OQ-xx: integrated mezzanine stack option (Hub-on-24-pin); RJ-45 remains the default/cabled PHY."

## 8. Gating checks before committing
- Component-height vs 14mm gap (confirm the Hub footprint clears the 24-pin's edge connectors).
- The mirrored-socket mated-pair net check (do NOT skip).
- +5VSB current + GND return across the connector (pin sizing) -- 3+7 looks comfortable.
- EMC: stacked-board loop area -- the 4-corner GND bond + 7 connector GNDs is the mitigation; do an EMC pass.
