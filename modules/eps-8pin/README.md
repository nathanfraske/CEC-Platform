# EPS 8-pin module

> **STATUS (2026-07-04, spec §2.8 v1.4.0 output-architecture revision, owner-ratified,
> BETA-2):** the per-cable board-mount **J_OUT1/J_OUT2** output headers (Molex Mini-Fit Jr
> 87427-0802, described extensively below as historical PCB context) are **RETIRED**. Each
> cable's output now crosses the ratified all-Keystone/TE connector-daughterboard interface
> (`docs/standard-tier-review/output-daughterboard-study-2026-07-04.md` §8.9–§8.10,
> `blade-fit-check-2026-07-04.md`): **3 rail clips + 3 GND clips per cable** (6 Keystone 3586
> SMT universal-entry blade clips, LCSC C238113, refs `TB{cable}1`–`TB{cable}6` — e.g. cable 1
> = `TB11`–`TB16`), each single-pin clip landing on the exact post-shunt net (`/SENSEC{n}_LO`)
> or `GND` its share of J_OUT used to carry. Applied via `scripts/gen-module-beta.py`'s
> `06-cable-power` leaf (generator edit + `--force` regen, not a hand edit); J_IN (the PSU-side
> input header) is unchanged. Netlist-verified: only `/SENSEC1_LO`, `/SENSEC2_LO`, and `GND`
> changed, with every other net byte-for-byte identical; ERC/audit-sch introduce zero new
> findings once `fp-lib-table` carries the `cec-Connector_Blade` line (added). `bom/
> eps8pin-module-BOM-jlcpcb.csv` updated (J_OUT rows removed, one `Keystone 3586` row added).
> Sense-return contacts are explicitly NOT added — the study's §5 decision box (e) is still
> open with the owner. **PCB follow-up (not done here):** the routed `.kicad_pcb` still shows
> the retired J_OUT connectors; it needs Update-PCB-from-Schematic + a footprint swap to the
> Keystone 3586 SMT land + a re-route of the cable-power corner before fab. The mating
> daughterboard (TE 63849-1 tabs) is a separate deliverable, tracked outside this board.
>
> Everything below this point describes the **PSU-side input header** (unchanged) and the
> alpha-era PCB layout built around the now-retired J_OUT connectors — read it as historical
> design rationale for J_IN/the sensing chain/the stackup, not as a description of the current
> output connector.

Standard-tier **per-cable** sensing module for the EPS (CPU) 8-pin power
connector. BOM target **$32** (100-qty). See spec
[§6.2](../../CEC-Platform-Ground-Truth-Spec.md) (sensing) and §8 (BOM).

Per CLAUDE.md's 2026-07-03 alpha/beta convention: this board is the **ALPHA**
line (validated prototype, as designed); refinements (the routing pass, etc.)
land as **BETA** revisions per the standard-tier beta plan
(`docs/standard-tier-review/SYNTHESIS-beta-plan.md`).

| Item | Decision |
|---|---|
| Tier | Standard |
| MCU | **ESP32-C6-MINI-1-N4** (v3.10; was ESP32-S3-MINI-1-N4R2). Native **USB-Serial-JTAG on GPIO13 (D+) / GPIO12 (D−)**; ADC1 = GPIO0–6. 24-pin + EPS may cost-down to C3-MINI once the NTC count is fixed. |
| Hub link | RJ-45 8P8C shielded FTP, locking boot (universal interface, J1) |
| Power path | Pass-through interposer: per cable a PSU-side **IN** + a load-side **OUT** 8-pin (2×4) header; **2 cables populated → 4 headers** (J_IN1/J_OUT1, J_IN2/J_OUT2). **Molex Mini-Fit Jr 87427-0802** right-angle header (`cec-Connector_Molex:Molex_Mini-Fit_Jr_87427-0802_2x04_P4.20mm_RA`, official Molex export, cross-checked — the modern part used on newer boards). **EPS12V pinout: pads 1-4 = GND row, 5-8 = +12V row** (fixed 2026-06-06 — see below). The 24-pin §2.8 interposer pattern (male board headers + a F-to-F bridging cable) is the working basis. |
| Control | CAN on pair 3 (classical 500 kbps in a Standard Hub), TJA1051T/3 transceiver (U2) |
| Sensing | **Per-cable INA238** (16-bit I²C, ≥1 kHz), 2 cables (U10/U11, distinct I²C addresses on one bus) — one across each cable's **0.5 mΩ** Kelvin shunt (RS1/RS2, §6.4), Vbus read on the load side. Each cable's four 12V pins bundle into the shunt (`SENSE_HI`→shunt→`SENSE_LO`); the four GND pins pass straight through. |
| Transient detection (§6.13) | **Per-cable analog DETECTION front-end** (v3.10, resolves OQ-9): off the same shunt, **INA181A2** gain-50 CSA (U20/U21) → **TLV7011** hysteresis comparator (U30/U31) → a board-shared firmware-settable **THRESH** (MCU PWM IO14 + R10 10 kΩ / C40 100 nF) → per-cable **DET** to an MCU GPIO latch, which ORs into the §6.10 FREEZE trigger. Flags a transient as a **binary event** (that it happened + the averaged envelope) — NOT the sub-ms waveform; magnitude/shape are an EPS **Pro/Max** SKU. |
| Streaming | RS-485 **not populated** (Standard); pair 2 (J1.4/5) left unused, terminated module-side |
| DETECT | **2.2 kΩ** precision (R1) — CAN-only link-capability code (§2.3, OQ-6 resolved), read on the Hub's 10 kΩ / 3.3 V divider. Poke-and-ack sense tap R7 (100 kΩ → IO10, OQ-28). |
| Protection | No per-pin PoE/over-voltage (Standard/Pro, §2.4 RESOLVED v2.0); low-cap ESD diode **D1** (PESD5V0S1BA, C5261083) on DETECT pin 8 (LOCKED v2.0). Enterprise/MC over-voltage rides the external uplink (OQ-7). |
| Decoupling | LP5907-3.3 LDO (U3). Matches the 24-pin gold standard: 10 µF board-entry bulk on +5VSB (C6) + 10 µF +3V3 bulk at the ESP32 (C7); 1 µF LDO in/out (C1/C2); per-IC 100 nF — ESP32 (C3), TJA1051T/3 VCC (C4) and VIO (C8), one per INA238 (C10/C11); 100 nF EN reset RC (C5). |
| Flash/debug | **USB-C** (J5) on the ESP32-C6 native **USB-Serial-JTAG** (D+ = IO13 / D− = IO12) + **BOOT/RESET buttons** (SW1/SW2, XKB **TS-1088-AR02016** / C720477; BOOT = IO9). VBUS ORs into +5VSB through D2 (SS34) so bench USB self-powers the board for flashing; CC1/CC2 = 5.1 kΩ UFP pulldowns. |
| Reset | ESP32-C6 internal BOD + EN RC (R2/C5); no external supervisor (a Hub-only part) |
| BOM target | $32 (100-qty) |

## Open questions touching this board

- **OQ-9 (RESOLVED, v3.10 §6.13):** EPS transient capture is the analog DETECTION
  ladder above — Standard sees that a transient happened (binary, into FREEZE),
  magnitude/shape are held to the EPS Pro/Max SKUs. (OQ-57..59 gate the ladder's
  threshold/firmware details.)
- **OQ-10 / OQ-12:** bundled-shunt vertical transition and high-current stackup
  for the ~40–55 A per-cable shunt sites (§6.7).
- **OQ-11:** per-module shunt part selection (value / TCR / tolerance / package /
  power) per the §6.4 table.
- **OQ-13:** energy-reporting scope (the 24-pin INA228 gives hardware energy;
  EPS energy would be firmware-integrated and must not be presented as total).
- *(OQ-6 module-ID encoding is RESOLVED — CAN-only modules = 2.2 kΩ.)*

## Status

Schematic is generated by `scripts/gen-modules.py` (shared Standard-module
backbone) and verified in-repo with the static connectivity audit
(`scripts/audit-sch.py`) and `kicad-cli sch erc` — clean apart from the
by-design GPIO0 service-pad label and the known generator `lib_symbol_mismatch`
noise. The **DRAFT** marker is present: PCB placement/routing geometry (incl. the
§6.8 four-wire Kelvin shunt taps and §6.7 high-current transitions) is done in
the KiCad 10 GUI; delete DRAFT to enforce ERC/DRC in CI.

An **initial PCB floorplan** is bootstrapped by `scripts/gen-module-pcb.py` (a
one-shot — the `.kicad_pcb` is hand-maintained in the GUI afterwards): **4-layer,
2 oz outer / 1 oz inner** (In1 = GND, In2 = 12 V plane), ~110 × 66 mm, with the
four Mini-Fit Jr 2×4 cable connectors inline (PSU-side IN on the top edge,
load-side OUT on the bottom — top→bottom 12 V flow through each cable's 2-pad
R_2512 shunt + INA238), the ESP + CAN + LDO + the flash front end (USB-C,
BOOT/RESET, ORing diode + CC) + the RJ-45 on the right, four M3 chassis-GND mounts
in the corners (cables inset so they stay clear), and a CEC copper logo on the
back. The ~40–55 A/cable 12 V path is what drives the 2 oz-outer copper choice
(1 oz alone runs hot near the top of that range). Next in the GUI: *Update PCB
from Schematic* to pull the decoupling passives, then place/route + pour (incl.
the §6.8 Kelvin taps and §6.7 high-current transitions).

Project-local library tables point at `../../lib` via `${KIPRJMOD}`.

## Update (2026-06-05) — brought to the Hub's part level + sourced

Applied the platform corrections the Hub Standard landed, and sourced the BOM:

- **D1 PESD5V0S1UL → PESD5V0S1BA** (SOD-323, **C5261083**) on the DETECT pin-8 ESD.
- **BOOT/RESET buttons SW1/SW2 → TS-1088-AR02016** (XKB, **C720477**), replacing the
  Panasonic EVQ placeholder. Same `cec-vendor:SW_Push` symbol, **netlist preserved**
  (SW1 GPIO0↔GND, SW2 EN↔GND through the new footprint).
- **BOM sourced 29/35** (`bom/eps8pin-BOM-jlcpcb.csv`): INA238 → **INA238AIDGSR /
  C2868250**, ESP32-S3-MINI-1-N4R2 → **C3013941**, TJA1051T/3 → C38695, LP5907 →
  C80670, SS34 → C8678, RJ-45 54602 → C2847314, USB-C → C2765186, and the passives
  (reusing the Hub's LCSC: 100nF C1525, 1µF C15849, 10µF C15850, 2.2k C25879, 10k
  C25744, 100k C25741, 5.1k C25905).

**Still to source (6):** RS1/RS2 the **0.5 mΩ 2512 shunt** (OQ-11 — value locked,
exact part open; the 24-pin uses Bourns CSS2H-2512, so the 0.5 mΩ sibling fits) and
J_IN1/2 + J_OUT1/2 the **Mini-Fit Jr** EPS power connectors (THT — hand-solder/consign).

ERC clean (benign generator `lib_symbol_mismatch` only). The schematic is now
**hand-sourced** — do NOT regenerate with `gen-modules.py` (it would revert the PESD
and button and drop the LCSC). PCB next: *Update from Schematic* to pull the TS-1088
footprint + the PESD value, then the layout/fab flow.

## PCB layout strategy (2026-06-05) — high-current 4-layer

The EPS carries **~30 A per cable** (4× Mini-Fit Jr 12V pins ≈ 9 A each, bundled into
each 0.5 mΩ shunt), so it is a high-current 4-layer:

- **Copper: 2 oz outer / 1 oz inner** (set in the stackup). 2 oz outers give the
  cross-section for the 12V/GND pours; the inner planes are huge-area so low-R at 1 oz.
- **Two whole GND planes (In1 + In2)** — same call as the 12VHPWR. Added as one
  `GND Plane` zone. Gives the return path for the ~30 A GND pins, the quiet reference
  plane under the INA238 Kelvin sense lines, and thermal spreading. **Fill in the GUI
  (`B`).**
- **12V IN/OUT on the *outers*, split at the shunt.** Per cable: a 12V_IN pour (top,
  4 IN pins → shunt high side) on F.Cu and a 12V_OUT pour (bottom, shunt low side →
  4 OUT pins); mirror both onto B.Cu and stitch to parallel them (2 oz × 2 ≈ 4 oz).
  The shunt sits on F.Cu across the IN/OUT split. **Not** an inner 12V plane — a single
  12V plane would short the shunt.
- **Vias:** a field of stitching vias per 12V pin and per shunt terminal (F↔B parallel);
  the GND pins stitch straight down into the two inner planes.
- **Kelvin sense:** a tight ~0.2 mm matched pair off the *inner* edges of each shunt,
  over the In1 GND plane, into the INA238 (§6.8).

Floorplan (generated): 2 cables on the left (each IN-top → shunt-mid → OUT-bottom),
control core (ESP / CAN / LDO / USB-C / RJ-45) on the right.

## Update (2026-06-06) — v3.10: ESP32-C6 MCU + §6.13 transient-detection front-end

Regenerated on the consolidated v3.10 spec. Net changes vs the 2026-06-05 sourcing:

- **MCU ESP32-S3-MINI-1-N4R2 → ESP32-C6-MINI-1-N4** (C5736265). Pin map
  netlist-verified: CAN_TX/RX → IO20/21 (pads 26/27), USB D+/D− → IO13/IO12 (pads
  18/17), I²C → pads 24/25, EN → pad 8, BOOT/IO9 → pad 23, DETECT_SENSE → pad 12,
  +3V3 → pad 3, THRESH_PWM/IO14 → pad 19. Footprint `cec-RF_Module:ESP32-C6-MINI-1`
  (vendored + 3D). ADC1 = GPIO0–6.
- **§6.13 per-cable detection front-end added** (2 cables): U20/U21 **INA181A2IDBVR**
  (C2058784, SOT-23-6, gain 50) + U30/U31 **TLV7011DBVR** (C702117, SOT-23-5
  comparator) + board-shared R10 (10 kΩ) / C40 (100 nF) THRESH RC off MCU PWM IO14,
  + per-IC bypass. Chain netlist-verified: shunt `SENSE_HI` → INA181 → comparator →
  `THRESH` (R10/C40/both comparators) → per-cable `DET` → MCU GPIO (IO22 pad 28 /
  IO23 pad 29).
- BOM regenerated (`bom/eps8pin-module-BOM-jlcpcb.csv`): **sourced 39/45**; still
  open are the 0.5 mΩ shunts (OQ-11) and the Mini-Fit Jr THT power headers.
- ERC = benign only (generator `lib_symbol_mismatch` + easyeda `pin_to_pin`
  Unspecified + the C6 NC pad + CAN-TXD `pin_not_driven`).

Generator `scripts/gen-modules.py` now emits the C6 + §6.13 backbone, so this board
round-trips again.

## PCB floorplan (2026-06-06) — CONDENSED, C6 + §6.13, dual GND, 3 mounts

The PCB floorplan was rebuilt + **condensed** from the v3.10 netlist via
`scripts/gen-module-pcb.py eps-8pin` (a CLI filter + a routed-board guard keep the
routed 12VHPWR untouched). The board had **zero routing**, so the bootstrap re-ran
cleanly. **99 × 44 mm — down from 110 × 66, a ~40 % area cut, and width kept under
100 mm.** Verified by render + DRC (and an in-loop courtyard/pad-clearance checker).

> J1 is the **platform FTP jack** — Kinghelm **KH-RJ45-58-8P8C** (LCSC **C2683360**),
> footprint `cec:RJ45_FTP_Shielded_Horizontal`, same as the Hub and 12VHPWR (was the
> unshielded Amphenol 54602). Its **SH1/SH2 shield tabs are tied to GND** (both-end
> shielding + grounding, matching the 12VHPWR). The shield tabs extend further than
> the old jack, so the board is 99 mm (not 98) to give them edge clearance while the
> mouth still overhangs.

What made it shrink:

- **Connectors overhang their edges.** The Mini-Fit Jr Horizontal footprint keeps
  its 2 pad rows (local y0/y5.5) and its 2 NPTH retention pegs (local y-4.2)
  on-board, but its ~13 mm body+mouth (out to local y-13.9) now hangs **off** the
  board edge — J_IN off the top, J_OUT off the bottom. Each connector needs only
  ~12.5 mm of board instead of its full ~22 mm courtyard. The **pegs are the hard
  limit** (they can't overhang), so the mouth overhangs ~7 mm, not the full body.
- **The RJ-45 mouth overhangs the right edge too** (same trick): its contacts +
  2 posts + 2 shield tabs stay on-board, the jack opening hangs ~5 mm off the edge.
  That reclaims the ~7 mm of board that used to sit under the jack body and is what
  pulls the width under 100 mm. (Height was traded up 40 → 44 mm so the electronics
  stack into a narrower column — the size/aspect trade you asked for.)
- **Side-by-side sense band** (not stacked): the 0.5 mΩ shunt sits **vertical
  (rot90) in the 12 V path** (current flows straight top→bottom through it); INA238
  (VSSOP-10, ~6.4 mm wide) sits to its left and the §6.13 pair (INA181A2 → TLV7011)
  stacks to its right — all Kelvin-tapping the same shunt. Collapses the per-cable
  band from ~16 mm tall to a single ~6 mm row, the biggest height saver.
- **3 M3 mounts**, not 4: the overhang fills the top/bottom edges across the cable
  region and the RJ-45 fills the right edge, so there's no clean 4th corner. One
  mount sits on the **left edge at mid-height** (the clear band between the J_IN and
  J_OUT courtyards); two sit in the **right corners**, freed by moving USB-C off the
  right edge. (Per the design decision to drop to 3 for the tightest size.)
- **USB-C (J5) moved to the TOP edge** (rot180 so the mouth overhangs −y and the
  pads stay on-board), which frees the right edge for the RJ-45 + the two corner
  mounts. RJ-45 (J1, "TO-HUB") is centered on the right edge, mouth overhanging it.
  BOOT/RESET (SW1/SW2) are stacked vertically (not side-by-side) so their pads don't
  mask-bridge in the narrowed mid-strip.
- Left **dead space reclaimed** (first cable origin x 20 → 9).

Unchanged fundamentals: **4-layer, F.Cu 2 oz / In1 1 oz / In2 1 oz / B.Cu 2 oz**;
one `GND Plane` zone over **In1 + In2** (12 V on the outers, split at each shunt),
emitted unfilled (*Fill All Zones* in the GUI); C6 has no antenna keepout
(wired-only) so GND fills under it; CEC logo + "4L 2oz/1oz" fab note on the back
(logo moved under the C6, off the cable-region through-hole pads).

**DRC** no structural hits (courtyard / clearance / copper-edge / mask all clean);
remaining are cosmetic silk (value-on-silk + dense-cluster text overlap — a GUI
silk-refinement task) and the benign `lib_footprint_mismatch`. The "unconnected"
items are the un-routed ratsnest (expected for a floorplan).

**Next in the GUI:** *Update PCB from Schematic* to pull the parts the floorplan
intentionally leaves for the GUI — the decoupling (C1–C8), the DETECT divider +
poke tap (R1/R2/R7), the D1 ESD diode, and the §6.13 per-IC bypass caps — then place
those, *Fill All Zones*, route (incl. the §6.8 four-wire Kelvin shunt taps and §6.7
high-current 12 V transitions), and re-DRC. The two PCIe SKUs use the same generator
path and can be condensed the same way when their turn comes.

## PCB floorplan (2026-06-06, widened to 96 × 37 mm in commit 14906cc) — RE-CONDENSED on the pegless 87427 connector

Once the power connector moved to the **pegless Molex 87427-0802** (no snap-peg NPTH
holes — see the pinout-fix note above), the floorplan was re-condensed: **99 × 44 → 96 × 35 mm
(−24 % area, ~−20 % height)** at the time of that pass. The board was later widened
**35 → 37 mm** (commit `14906cc`, the "loop iteration 2" placement revision, to open a
wider control→sense spine channel) — the committed board today measures **96 × 37 mm**
(−18.5 % area, −15.9 % height vs the original 99 × 44 mm), not 96 × 35. The win is
entirely the pegs — the old 5569 footprint reserved
~7–11 mm of board on each connector's *mouth* side for the snap-peg holes (which can't overhang);
the 87427 keeps only its **pad rows on-board and overhangs the whole body/mouth**, so each cable's
J_IN/J_OUT pull to ~4 mm from the top/bottom edges and the cable column collapses ~22 → ~14 mm.
This board has **all 45 schematic parts placed** (the decoupling no longer waits for
*Update-from-Schematic*); **0 structural DRC hits** (remaining are the usual cosmetic silk +
benign `lib_footprint_mismatch`). Verified by render + DRC.

- **Connector rotations FLIP vs the old footprint** (the 87427 is mirrored): **J_IN = rot180**
  (mouth overhangs the TOP edge, GND row at y≈4, +12V row at y≈9.5) and **J_OUT = rot0**
  (mouth overhangs the BOTTOM, +12V row at y≈H−9.5, GND row at y≈H−4). J_OUT sits at
  `Xc+12.6` so the +12V pad columns (pads 5–8) stay vertically aligned with J_IN — **12 V flows
  straight down through the shunt**. (The old pegged board used J_IN rot0 / J_OUT rot180.)
- **Sense band** between each cable's IN/OUT (real courtyards): INA238 (Kelvin-taps the shunt,
  left) · 0.5 mΩ shunt (rot90, in the 12 V path) · INA181A2 + TLV7011 (§6.13, right), each with
  its 100 nF bypass tight to it.
- **Core (right):** ESP32-C6 (U1) mid; USB-C (J5) top edge; CAN (U2) + VBUS ORing (D2/C9) +
  CC (R8/R9) in the top band; LP5907 (U3) + LDO caps mid; BOOT/RESET (SW1/SW2) bottom; the
  **RJ-45 (J1) overhangs the right edge** (box ≈ y[5.6, 21.6]); the DETECT front-end (D1/R1/R7)
  sits just below it.
- **ESP antenna keepout DROPPED** (no wireless, per the design): its courtyard is trimmed to
  the body so GND fills under the antenna and parts pack closer. *Further headroom not spent:*
  the antenna end (no pads) could **overhang a board edge** to push toward ~90 × 33 (−30 %).
- **3 M3 mounts:** two on the clear left strip (the connector overhangs eat the top/bottom edges
  across the cable region; the RJ-45 eats the right), one bottom-right corner below the RJ-45.
- Stackup / copper unchanged: **4-layer, F.Cu 2 oz / In1 1 oz GND / In2 1 oz GND / B.Cu 2 oz**;
  12 V on the outers split at each shunt; one `GND Plane` zone over In1+In2 (emitted unfilled —
  *Fill All Zones* in the GUI).

**Routing strategy (candidates) — for when you route this board:**

1. **+12 V high-current (per cable, ~30 A):** J_IN pads 5–8 → shunt HI → [RS] → shunt LO →
   J_OUT pads 5–8, straight down the aligned column. A **12V_IN F.Cu pour** (J_IN → shunt high)
   and a **12V_OUT F.Cu pour** (shunt low → J_OUT), each **mirrored on B.Cu + via-stitched**
   (2 oz × 2 ≈ 4 oz). The shunt bridges the IN/OUT split on F.Cu — **never pour 12 V on an inner**
   (it would short the shunt). Via field at each +12 V pad and shunt terminal.
2. **GND return:** the 16 connector GND pins (pads 1–4 ×4) + all IC/cap grounds stitch straight
   down into the two inner GND planes; keep them solid (also the quiet reference under the Kelvin
   taps).
3. **Kelvin sense (per shunt):** INA238 (left) and INA181 (right) each tap the **inner edges** of
   the shunt pads as a **tight ~0.25 mm matched pair over the In1 GND plane** — short, symmetric,
   not crossing the 12 V pour (the SENSE*_HI/LO nets are shared with the 12 V force; the Kelvin
   benefit is in *where* you tap).
4. **Control→sense "spine":** +3V3, I²C SCL/SDA (ESP → U10 → U11), THRESH (ESP → both comparators),
   DETC1/DETC2 (comparators → ESP) all cross right-core → left sense band. Inners are GND, so route
   this on the **outers along the mid-height y≈17 lane** between J_IN and J_OUT (the only clear
   horizontal channel — the connector backs are full of THT pads). Bundle the slow/DC signals;
   keep THRESH (an analog ref) over GND, away from the 12 V switching edges.
5. **CAN:** CAN_H/L = J1 ↔ U2 (tight pair over GND); CAN_TX/RX = U2 ↔ ESP. No 120 Ω termination on
   the module (it lives at the Hub).
6. **USB FS pair:** USB_DP/DM = J5 ↔ ESP, length-matched on F.Cu over GND, short (J5 is right above
   the ESP); CC1/CC2 (R8/R9) and VBUS → D2 → C9 → +5VSB at the connector.
7. **+5VSB / DETECT:** +5VSB short F.Cu in the core (RJ-45 VCC + USB ORing → LDO/CAN); DETECT
   cluster (D1/R1/R7) at J1.8, DETECT_SENSE joins the spine.

The floorplan is a hand-maintained bootstrap (made by a one-shot condensed-placement pass that
reuses `gen-module-pcb.py`'s helpers; not folded into the shared generator). From here it is
GUI-maintained.

## Update (2026-06-06) — EPS12V pinout fix + formal Molex 87427-0802 footprint

The PCB's power-connector pinout was **flipped** vs the EPS12V/EATX12V standard, and the
connector was on an approximate generic footprint. Both fixed (user supplied + cross-checked
the official Molex part):

- **Pinout corrected to EPS12V.** Was +12V on pads 1-4 / GND on 5-8 (the flipped
  assignment); now **GND on pads 1-4, +12V on pads 5-8** across all four connectors
  (J_IN1/J_OUT1/J_IN2/J_OUT2), matching the Molex Mini-Fit Jr circuit numbering the EPS12V
  standard uses. Netlist-verified per connector: pins 1-4 → `GND`, pins 5-8 → `SENSE*_HI`
  (J_IN, PSU side) / `SENSE*_LO` (J_OUT, load side); the shunt path `HI → RS → LO` and the
  §6.13 INA181 taps are unchanged (they tap the SENSE nets, not specific pins). The
  **generator was fixed at the source** (`scripts/gen-modules.py` `PINMAP["eps-8pin"]` →
  `12V:[5,6,7,8] / GND:[1,2,3,4]`) so a future EPS regen no longer reverts the pinout.
  *(PCIe's separate PINMAP entry is untouched.)*
- **Footprint → official Molex `87427-0802`** (`cec-Connector_Molex:Molex_Mini-Fit_Jr_
  87427-0802_2x04_P4.20mm_RA`, vendored from Molex's KiCad export + the `874270802` STEP at
  `lib/3dmodels/Connector_Molex.3dshapes/`). The interim `5569-08A_39301080` part (from the
  first upload) was superseded and removed. The two shared Molex footprints (the 24-pin 2×12
  and the PCIe 2×4) are **untouched**.
- **ERC** still the 2 pre-existing errors (GPIO0 service-pad `pin_not_driven` + one
  `pin_not_connected`) + benign generator `lib_symbol_mismatch` / easyeda `pin_to_pin`
  noise — no new violations.

> **⚠️ PCB committer — re-place the 4 connectors.** The formal `87427-0802` footprint is
> **mirrored** vs the old `5569-08A2` (pads run in −x, the 2nd row sits at −y, the
> body/shroud is on the +y side) **and has NO snap-peg NPTH holes** (the old footprint had
> two retention pegs at local y−4.2, which the condensed floorplan's overhang strategy used
> as the hard edge limit). So *Update PCB from Schematic* will move every connector pad —
> **re-place all four (J_IN top edge / J_OUT bottom edge), re-route the 12 V + GND + Kelvin
> sense, and re-derive the edge overhang** (retention is now via the THT solder tails, not
> pegs, so the mouth can overhang further). Confirm the keyed +12V row (pads 5-8) faces the
> intended way before powering.

## Candidate generator (2026-06-06) — `scripts/gen-eps-condensed.py` + routing plan

The condensed floorplan is now produced by a **reproducible generator** instead of a
hand-bootstrap, and it ships a **routing game-plan** so the board is ready to route:

```
python3 scripts/gen-eps-condensed.py          # writes the .kicad_pcb + eps-routing-plan.png
python3 scripts/gen-eps-condensed.py --no-plan # board only
```

What it does (reuses `gen-module-pcb.py`'s emit helpers without touching the shared generator):

- **FRAME** — the pegless-87427 condensed layout (J_IN rot180 / J_OUT rot0 so the +12V
  columns align; per-cable sense band; ESP/CAN/LDO/RJ-45 core). 96 × 37 mm (widened
  from the generator's original 96 × 35 mm in commit `14906cc` for spine routing), 3 M3 mounts.
- **PASSIVE ENGINE** — every decoupling / RC / pull-up / ESD passive is placed in its
  **owner IC's cluster on the power-pin side**, from a netlist-verified ownership spec
  (`PASSIVE_SPEC`: each part → the IC it serves + the exact net it must share). At build
  time `verify_passives()` re-checks all 25 against the live netlist (**25/25 verified**)
  so the clusters can't silently drift from the schematic. Reproduces the validated
  placement (**0 structural DRC**; remaining hits are the usual cosmetic silk).
- **ROUTING CANDIDATES** — drawn as guide graphics **in the board** on toggleable user
  layers, so they're visible while routing: 12V IN/OUT pour outlines (`Dwgs.User`), the
  Kelvin sense pairs off each shunt's inner edges (`Cmts.User`), the control→sense spine
  +3V3 / I2C / THRESH / DETC (`Eco1.User`), and CAN + USB (`Eco2.User`).
- **`eps-routing-plan.png`** — a board-accurate visualization of the full game plan: the
  12V pours, GND stitching, Kelvin pairs, the spine, CAN and USB over the real placement,
  with the **routing order (1→9)**, the **netclass table** (Power12V pour / GND plane /
  Sense 0.25 / Power 0.5 / Signal 0.22 / CAN / USB) to add to the empty `.kicad_pro`, and
  the **SI keep-aways** (Kelvin & THRESH off the 12V pour edges; spine in the y16–21.5 split
  gap, hop a shunt column on B.Cu; USB length-match; CAN pair, Hub-side termination).

It is still a one-shot bootstrap — once the board carries tracks/vias the generator
**refuses to overwrite** (pass `--force` to override); from the first route it is
GUI-maintained. The routing guides live on non-copper layers, so they never affect DRC or
the copper; delete the user-layer graphics once routing is done if you don't want them.

## Netclasses + design rules (2026-06-06) — `.kicad_pro` / `.kicad_dru`

The previously-empty `.kicad_pro` now carries the routing netclasses, and a matching
`.kicad_dru` makes DRC enforce them:

| Netclass | track | via | clr | members |
|---|---|---|---|---|
| **Power12V** | 2.5 mm (pour) | 0.9/0.5 | 0.2 | `/SENSEC*` — the ~30 A 12 V pours, split at each shunt |
| **GND** | 0.5 mm (plane) | 0.9/0.5 | 0.2 | `GND` |
| **Power** | 0.5 mm | 0.8/0.4 | 0.2 | `+3V3`, `+5VSB`, `/VBUS` |
| **Signal** | 0.22 mm | 0.6/0.3 | 0.2 | I²C, THRESH, DETC/DETAMP, DETECT, CAN_TX/RX, EN, CC |
| **CAN** | 0.25 mm | 0.6/0.3 | 0.2 | `/CAN_H`, `/CAN_L` (coupled pair) |
| **USB** | 0.25 mm, **diff gap 0.13** | 0.6/0.3 | 0.2 | `/USB_D_P`, `/USB_D_N` (differential pair) |

**Matched pairs:**
- **USB FS pair is now an auto-recognized differential pair.** The nets were renamed
  `/USB_DP → /USB_D_P` and `/USB_DM → /USB_D_N` (the repo's `_P`/`_N` convention, same as
  the 12VHPWR sense pairs), so KiCad's differential-pair router pairs them automatically;
  the USB netclass sets width 0.2 / gap 0.13 and the `.kicad_dru` flags long uncoupled runs.
  (Pure label rename — ERC clean, connectivity identical: `/USB_D_P` = {J5.A6, J5.B6, U1.18},
  `/USB_D_N` = {J5.A7, J5.B7, U1.17}.)
- **CAN_H / CAN_L keep their standard names** — H and L are semantically asymmetric (defined
  dominant/recessive levels), so renaming them to P/N would be wrong. They're routed as a
  **tightly-coupled pair** by hand to the RJ-45 via the CAN netclass; the only termination is
  the Hub's split 120 Ω, never on the module.
- **The Kelvin sense pairs are hand-matched, not a netclass pair.** Each INA238/INA181 IN+/IN−
  is the `/SENSEC*_HI` / `/SENSEC*_LO` net — the *same* net as the 12 V force — so they can't be
  a separable diff-pair net. Tap the shunt's inner edges symmetrically and draw the two stubs
  as a matched 0.25 mm pair by hand (a Power12V track-width floor is deliberately omitted in
  the `.kicad_dru` so these thin taps aren't false-flagged; rail ampacity comes from the pour
  copper area, IPC-2152).

`.kicad_dru` rules: **Power min width** (0.5 mm floor on the Power class), **USB diff-pair gap**
(0.1–0.2 mm), and an explicit *no* width floor on `/SENSEC*` (pours + Kelvin taps). DRC is clean
(0 structural) with the netclasses active.
