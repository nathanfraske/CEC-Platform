# 12VHPWR Standard — Prototype V1 fab package

Tagged fab snapshot of `modules/12vhpwr-standard` as sent for the first prototype run.
Generated with `kicad-cli` (KiCad 10) from the board at this commit.

## Order spec
- **PCB:** 4-layer, 1.6 mm, ENIG, matte-black soldermask.
- **⚠️ Copper: 2 oz OUTER / 1 oz inner.** The six +12V lanes are designed as 2.5 mm on
  F.Cu **plus** 2.5 mm mirrored on B.Cu, paralleled at **2 oz**, to carry ~50 A
  (600 W / 12 V; IPC-2221, <10 °C rise). JLCPCB's 4-layer default is 1 oz all layers —
  **you must select 2 oz outer copper** at order time or the high-current lanes are under-spec.
- **Stackup:** 4-layer **12V / GND / GND / 12V** — F.Cu (2 oz, 12V lanes + signals),
  GND1 plane (`GND1.g1`), GND2 plane (`GND2.g2`), B.Cu (2 oz, 12V mirror). Both inner
  planes are solid GND, so each 12V outer runs directly against a ground plane.
- **Min track / clearance as built:** 0.25 mm sense / 0.2–0.25 mm clearance; 12V lanes 2.5 mm.
- **Controlled impedance: not required.** USB D± is a length-matched FS pair, CAN is a short
  120 Ω-terminated stub (≤1 Mbps), and the INA240 sense pairs / ADC lines are near-DC.

## Contents
| File | Purpose |
|---|---|
| `gerbers/` | Gerber set (X2) + Excellon drill (`PTH.drl`, `NPTH.drl`) + `.gbrjob` |
| `12vhpwr-standard-proto-v1-gerbers.zip` | Same set zipped — upload this to JLCPCB |
| `12vhpwr-standard-BOM.csv` | JLCPCB BOM (Comment / Designator / Footprint / LCSC) — 28 lines, all sourced |
| `12vhpwr-standard-CPL.csv` | Placement file (Designator / Mid X / Mid Y / Layer / Rotation) — 77 placements |

## Assembly notes
- BOM is **100 % LCSC-sourced** (28 grouped lines, 77 placements) **except J3/J4** — see below.
  3 fiducials (FID1–3) are on the board for placement alignment; they carry no part and are
  excluded from the BOM and CPL.
- **THT / hand assembly:** J1 RJ-45 (Kinghelm KH-RJ45-58, shielded FTP), J5 USB-C, SW1/SW2
  buttons. The rest is SMT.
- **⚠️ J3 / J4 (12V-2×6, Molex 2191161161) are CONSIGNED** — not in the JLCPCB catalog, so they
  appear in the CPL with no LCSC. **J3** (board-mount right-angle male IN) is hand-soldered;
  **J4** is a captive soldered output pigtail to the GPU (hand-assembled by definition).
- **NPTH** (`NPTH.drl`): the 3× M3 mounting holes + the RJ-45 locating posts (non-plated).

## Pre-power check
- **12V-2×6 pin assignment: pins 1–6 = +12V, 7–12 = GND.** Confirmed **PCIe CEM5.1 / 12VHPWR
  pin-compliant** — the schematic ties 7–12 to the GND plane and 1–6 to the sensed +12V, matching
  the standard. Safe to power.

## Known non-blocking items (do not gate the proto run)
- 15 cosmetic silk DRC warnings (silk-near-edge on the edge connectors + silk-over-copper on a
  few dense clusters). Trim on the next rev.
- Shunt RS1–6 = Bourns CSS2H-2512R-1L00F (1 mΩ, ±1 %, 75 ppm) — the spec §6.4 candidate; OQ-11
  is still formally open, and validating this part is a goal of this prototype.
