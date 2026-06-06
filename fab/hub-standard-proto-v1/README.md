# Hub Standard — Prototype V1 fab package

Tagged fab snapshot of `hubs/hub-standard` as sent for the first prototype run.
Generated with `kicad-cli` (KiCad 10) from the board at this commit.

## Order spec
- **PCB:** 4-layer, 1.6 mm, ENIG, matte-black soldermask.
- **Stackup:** JLCPCB standard 4-layer 1.6 mm — F.Cu / 0.21 mm prepreg / In1 (GND plane) / 1.065 mm core / In2 / 0.21 mm prepreg / B.Cu, FR-4 Er ≈ 4.5, 1 oz outers.
- **Copper:** F.Cu (`.gtl`), In1 GND plane (`GND.g1`), In2 signal (`In2_Cu.g2`), B.Cu (`.gbl`).
- **Min track / clearance as built:** 0.2 mm / 0.2 mm; power trunk 1.0 mm.
- **Controlled impedance: not required.** USB D± ≈ 95 Ω diff (within the FS 90 Ω ±15 % window) and CAN ≈ 104 Ω (short stub, ≤1 Mbps, 120 Ω-terminated bus ~matching the Cat5e cable). All other signalling is slow/DC.

## Contents
| File | Purpose |
|---|---|
| `gerbers/` | Gerber set (X2) + Excellon drill (`PTH.drl`, `NPTH.drl`) + `.gbrjob` |
| `hub-standard-proto-v1-gerbers.zip` | Same set zipped — upload this to JLCPCB |
| `hub-standard-BOM.csv` | JLCPCB BOM (Comment / Designator / Footprint / LCSC) — 37 lines, all sourced |
| `hub-standard-CPL.csv` | Placement file (Designator / Mid X / Mid Y / Layer / Rotation) |

## Assembly notes
- BOM is **100 % LCSC-sourced** (37 grouped lines, 77 placements). 15 Basic/Preferred, the rest Extended.
- **THT connectors** — 4× RJ-45 (Kinghelm KH-RJ45-58), J1/J8 JST-XH, J7 JST-PH (S5B right-angle), J6 USB-C, SW1/SW2 buttons — need THT/hand assembly; the rest is SMT.
- **NPTH** holes (`NPTH.drl`, 3.2 mm): the 4× M3 mounts + the RJ-45 locating posts (non-plated — fixed in the footprint).
- ⚠️ Pre-order check: confirm the 12V-2x6 / shield-tab... *(N/A for the Hub)* — verify the FTP shield-tab grounding and that the RJ-45 MPN (C2683360) is still in JLCPCB stock at order time.

## Known non-blocking items (do not gate the proto run)
- 29 cosmetic silk DRC warnings (silk-near-edge on the edge connectors + 5 silk-over-copper on TH1/C1/C8). Trim on the next rev.
- 2 ERC `endpoint_off_grid` on the off-grid `PWR_FLAG` stamps (functional).
