# Hub Standard

Tier 1 of 4. The mainstream Hub: 4 ports, classical CAN, USB Full Speed.
Canonical detail in spec [§4](../../CEC-Platform-Ground-Truth-Spec.md). All
v1.1 decisions carry forward unchanged **except connector and cabling**.

| Item | Decision |
|---|---|
| Tier | 1 of 4 |
| MCU | ESP32-S3-WROOM-1-N16R8 (16 MB flash + 8 MB PSRAM; antenna keepout honored for future Wi-Fi). MINI-1 has no 16 MB SKU, so the aggregation Hub uses WROOM; modules stay on MINI-1. |
| Ports | 4× RJ-45 8P8C, locking boot (was Mini-Fit Jr 12-circuit) |
| Protocol | Classical CAN @ 500 kbps over the CAN-FD-capable TJA1462A |
| Termination | Fixed 120 Ω split at the Hub |
| Host link | USB Full Speed |
| Bulk power | Dedicated 2-pin +5VSB power-in from the 24-pin module; distributes to the 4 ports over RJ-45 VCC (§2.7, OQ-1 locked) |
| RS-485 | **Not populated** (Standard); pair 2 unused, terminated at the module side |
| Regulator | LP5907 LDO |
| Hold-up | 4700 µF / 16 V aluminum electrolytic on the isolated `+5V_HOLD` node (Panasonic EEVFK1C472M, LCSC C401967, CP_Elec_16x17.5). Chemistry corrected "polymer" → electrolytic, **ratified spec v1.9** (4700 µF polymer is unobtainable; electrolytic is right for a diode-isolated reservoir feeding the LDO). |
| Surge cap | 470 µF on the shared `+5VSB` distribution rail (rides out module load-steps; LCSC C116423, CP_Elec_6.3x7.7) |
| Inrush | TPS2121 mux soft-start (`C_SS` = 2.2 µF) — **supersedes** the v1.1 discrete 1 Ω 1 W series resistor (the mux ramps the bulk-cap charge). Spec reconciled 2026-06-04. |
| Reverse polarity / isolation | TPS2121 OR-mux blocks reverse current on the source side; **D1** Schottky isolates the `+5V_HOLD` reservoir downstream. D1 is **SB120** (1 A / 20 V) as built; **SS14** (1 A / 40 V) is a drop-in higher-margin alternative — both adequate on the 5 V rail. |
| Supervisor | TPS3839K33 (3.3V-rail brownout/POR), RESET → ESP32 EN |
| Storage / identity | ESP32-S3-WROOM-1 internal 16 MB flash + 8 MB PSRAM; factory MAC + database (no eFuse, no secure element) |
| LEDs | 7× SK6812 MINI-E RGB chain, firmware current cap (§2.5 / OQ-2). Data line 3.3 → 5 V level-shifted: **U6 (SN74AHCT1G08**, both inputs tied = AHCT buffer; VCC = +5VSB, C14 100 nF decap) + **R14** 330 Ω series into DL1.DIN — the ESP32's 3.3 V GPIO is below the 5 V SK6812 V_IH (0.7·VDD ≈ 3.5 V), so the buffer guarantees a clean 5 V data high with no LED dimming. (74AHCT1G34 was the first pick but isn't on JLCPCB; the 1G08-as-buffer is the stocked equivalent in the same SOT-23-5 land.) |
| Service button | Hidden, GPIO0 (download mode) |
| Mounting | 4× M3 corner holes, chassis-grounded (`cec-MountingHole:MountingHole_3.2mm_M3_Pad_Via` — pad + stitching vias to the In1 GND plane; PC-standard fastener, spec v1.10) |
| PCB | 4-layer 1.6 mm, ENIG, matte black |
| BOM target | ~$36 (100-qty) |

## 24-pin dual-feed — Hub-side workaround options

The 24-pin module is both the bulk 5VSB source (JST) and a module on a port, so
its RJ-45 VCC can parallel the JST feed (spec §2.7 v3.3). The clean fix is at the
source (24-pin rev3: RJ-45 VCC no-connect), and for the prototype the rev2
bring-up mitigations apply. If you want the **Hub** robust against any
source-module regardless of its wiring, options in order of cost:

1. **Move port VCC distribution to the mux *input* (pre-mux, `5VSB_RAW`).** Ties
   the RJ-45 VCC and the JST to the same node, so the mux is no longer bypassed
   (kills the mux-defeat and the USB-only back-feed). Doesn't remove the cable-R
   current split, but preserves mux integrity. Zero added parts; caveat: ports
   aren't powered on USB-only bench (fine — no modules attached then).
2. **Per-port OR-ing diode on VCC** (Hub→port). A low-drop Schottky (or ideal-
   diode IC) in series with each port's VCC lets the Hub feed modules but blocks
   any module back-feeding the Hub — eliminates the parallel path for any
   source-module. Cost: ~0.3–0.4 V drop on module VCC (LP5907 / SK6812 tolerate
   ~4.6 V), or a small ideal-diode IC for near-zero drop.
3. **Diode on one designated power-source port only.** If the 24-pin always lands
   on a fixed port, block only that port — no drop on the other three. Trades
   any-port flexibility for that port.

Recommendation: rely on the 24-pin rev3 source fix; the Hub diode is insurance.
The current prototype Hub needs no change if the rev2 bring-up mitigation is used.

## Open questions touching this board

- **OQ-1 (locked 2026-05-30):** the Hub takes bulk 5VSB on a dedicated 2-pin
  power-in connector from the 24-pin module and distributes 5VSB to its 4 ports
  over RJ-45 VCC (spec §2.7). The single-pin trunk concern is resolved.
- **OQ-2:** firmware LED current cap value / max LED state to budget.

## Status

> **Status (2026-06-04 — schematic complete + ERC-clean; PCB placed and fully
> routed (DRC: 0 unconnected), in pre-fab review. The `DRAFT` marker still
> skips CI ERC/DRC.):** RJ-45 re-cut COMPLETE (4 ports + the 2-pin
> `CEC_PWR_IN_2P` 5VSB power-in). MCU is **ESP32-S3-WROOM-1-N16R8** (symbol +
> footprint vendored, antenna keepout honored — all 4 layers, off-board left).
> 5VSB front-end built: TPS2121 mux (PSU/USB OR-in) → **D1** isolation Schottky
> → 4700 µF hold-up on the isolated `+5V_HOLD` node → LP5907; 470 µF `C_bulk`
> surge cap on the shared `+5VSB`; blackout-sense divider → GPIO8. **ERC: 0
> errors.** USB ESD (D6) + per-port DETECT ESD (D2–D5) populated; J2–J5 on the
> FTP shielded footprint.
>
> **Pre-fab review (2026-06-04):** found and fixed the netclass-pattern bug
> (Power/CAN/USB patterns lacked the `/` prefix → rail nets fell into Default,
> so DRC was blind to under-width power traces). With it fixed DRC now reports
> the real punch-list:
> - **38 `track_width` errors** on the power nets — the 5VSB trunk (`/5VSB_RAW`,
>   0.4 mm) needs a pour or ≥1.5 mm; `/USB_VBUS` and `/+5V_HOLD` need ≥0.5 mm.
> - **Ground/return-path:** only In1 is poured and it reads as fragmented
>   (likely stale fill — `kicad-cli` can't refill). **Refill zones in the GUI
>   (`B`) first**, confirm In1 is one island, then widen/pour the 5VSB trunk on
>   F.Cu. CAN (CAN_H/L) and USB (D±) are 100 % on F.Cu over In1, 0 vias — good.
>   The slow/don't-care lines (DETECT/LED/GPIO/EN) ride In2 under In1 — also OK.
>   Power (+5VSB/+3V3/USB_VBUS) is currently long thin traces on **B.Cu**; move
>   it to a F.Cu pour (LAYOUT-GUIDE §"Power routing").
> - **CAN_RX/CAN_L** routed ~0.03–0.13 mm from the board edge — pull in.
> - Tent the via-in-pad on **C1** (4700 µF); add a 2nd GND via at **D6**; silk
>   cleanup on the RJ-45 shield pads + board-edge silk.
>
> Netclasses (Power/USB/CAN — patterns fixed), the `.kicad_dru`, and
> `LAYOUT-GUIDE.md` are in. 4-layer 1.6 mm, In1 = GND plane (EMC — see
> LAYOUT-GUIDE.md). Remaining before fab: the GUI pour/route pass above, then
> drop the `DRAFT` marker.
>
> **Update (2026-06-05):** the GUI pour/route pass above is largely DONE — In1
> refilled to **one solid island**, `+5VSB` widened to 1.0 mm, and the
> `/5VSB_RAW` trunk taken to a fat trace. **DRC: 0 `track_width`, 0 unconnected**
> (remaining is silk cosmetics + one stray `/USB_VBUS` stub to delete). **SK6812
> data level shifter ADDED** (U6 SN74AHCT1G08 AND-as-buffer + R14 330 Ω + C14
> 100 nF; ERC + netlist verified: ESP LED-data GPIO IO25 → U6 → R14 → DL1.DIN,
> VCC on +5VSB).
>
> **BOM now fully sourced for JLCPCB assembly** (2026-06-05): every one of the 33
> lines carries an LCSC part (15 Basic/Preferred, 18 Extended; ~$12.11/board in
> parts, ESP32 = $5.15 of it). Files in `bom/`: `bom.csv` (tracking) and
> `hub-standard-BOM-jlcpcb.csv` (Comment/Designator/Footprint/LCSC upload). Part
> reconciliations made while sourcing: **U6** 74AHCT1G34 → SN74AHCT1G08 (1G34 not
> on JLCPCB); **U2** populated as **TJA1051T/3** (C38695, matches the as-drawn
> symbol; diverges from the TJA1462A platform lock — see action items); **D2–D5**
> PESD5V0S1UL → **PESD5V0S1BA** (the SOD-323 sibling; UL isn't stocked in SOD-323);
> **D1** SB120 → **SS14** (C2480, Basic); **SW1/SW2** EVQ-PU → **TS-1088** (C720477,
> Basic; footprint repointed); **R3/R4** 60 Ω → 60.4 Ω (nearest 1%). Stock to
> re-check before a volume run: C1 4700 µF (≈385) and U4 TPS3839K33 (≈120).
>
> **PCB to-do (GUI):** "Update PCB from Schematic" (pulls U6/R14/C14 and swaps
> SW1/SW2 to the TS-1088 land), place + route the new parts near DL1, re-pour,
> re-DRC, drop `DRAFT` — then "Generate Placement Files" (CPL) + gerbers and the
> JLCPCB BOM/CPL set is complete. (The 2 new `lib_symbol_mismatch` on R14/C14 are
> the same benign class as the existing 28 — clears with GUI Tools → Update
> Symbols from Library.)

Library-driven schematic capture can be drafted in-repo (then verified with ERC
and the netlist); PCB routing geometry is done in the KiCad 10 GUI. Project files
land here (`hub-standard.kicad_pro` / `.kicad_sch` / `.kicad_pcb`) with
project-local `sym-lib-table` / `fp-lib-table` pointing at `../../lib` via
`${KIPRJMOD}`.
