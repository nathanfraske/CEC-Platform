# Hub Standard — Placement & Routing Guide

This board is **not** the 24-pin interposer. There is no high-current spine and
no Kelvin analog: it is a low-current (~3 A max), low-speed (USB Full-Speed
12 Mbps, classical CAN 500 kbps) aggregation board. So the hard parts are not
routing density — they are (1) the **ground plane** for EMC, (2) the **5VSB
power + isolation/hold-up topology**, (3) the **WROOM antenna keepout**, and
(4) keeping the **4 ports' CAN** and the **USB pair** clean.

## Do we need 4 layers? — Yes, but for the plane, not the routing

The routing genuinely does **not** need 4 layers (no high-speed nets, low part
count, ~3 A power). The reason to keep 4-layer is the **uninterrupted L2 ground
plane**:

- **EMC.** This is the cable aggregation point — 4 RJ-45 ports, each driving a
  CAN pair onto ~1 m of cable. A solid GND plane gives every CAN/USB signal a
  tight return directly beneath it and cuts common-mode emissions. It is the
  partner to the spec's FTP-shield intent (OQ-15); a 2-layer board undercuts it.
- **Future Wi-Fi.** The WROOM module wants a clean ground reference under its
  non-antenna pins; a noisy 2-layer board risks coupling into 2.4 GHz.
- **Power.** A 5VSB pour/plane makes the 4-port ~3 A distribution low-impedance.

**2-layer is viable** for a pure functional bring-up (solid bottom GND pour,
top-side power), saving ~$15-20 per 5-board JLCPCB proto — at the cost of EMC
margin and more layout discipline (keep the bottom pour solid, minimize bottom
routing). Spec §4 / the README lock 4-layer; keeping it needs no change, so this
guide assumes **4-layer 1.6 mm**. Dropping to 2-layer is a spec-revision call —
only worth it if cost is a hard driver and EMC can wait.

Suggested stackup — **JLC04161H-7628**, JLCPCB's default 4-layer 1.6 mm:
**1 oz outer (L1/L4), 0.5 oz inner (L2/L3)**. 0.5 oz inner is the standard,
cheapest option and the right call here (see "Copper weight" below).
- **L1 (F.Cu, 1 oz):** components, signals, **and the ~3 A 5VSB distribution** —
  keep the heavy power on the thick outer copper.
- **L2 (In1, 0.5 oz):** solid GND plane — the deliverable. 0.5 oz is fine for a
  plane (return current spreads out; ampacity is a *trace* concern, not a plane
  one). Keep it unbroken under U1, the diff pairs, and the CAN bus.
- **L3 (In2, 0.5 oz):** signal crossings + GND fill. An optional +5VSB *assist*
  pour is OK (a wide pour carries current even at 0.5 oz), but don't let it be
  the only path for the trunk.
- **L4 (B.Cu, 1 oz):** spillover signals + GND fill, stitched to L2.

**Copper weight — 0.5 oz inner is fine.** It is JLCPCB's default (cheaper than
1 oz inner) and nothing here needs more: the L2 GND plane doesn't care about
thickness, and the only heavy net (~3 A 5VSB) lives on the 1 oz outer layers.
Rule of thumb: a ~3 A *trace* on 0.5 oz internal would have to be impractically
wide (internal copper derates ~50 % vs external), so never bury the trunk as an
inner trace — but a *pour/plane* at 0.5 oz is fine. Keep power on L1; let the
inners be GND + signal.

## Place these first — mechanical anchors (set by the enclosure, not electrons)
- **4× RJ-45 (J2–J5):** along the back edge, evenly spaced, cable exit outward.
- **USB-C (J6):** front/side edge for the host cable; **hard against U1** (short
  USB pair).
- **2-pin power-in (J1):** near where the 24-pin module's 5VSB cable enters.
- **4× M2.5 mounting holes:** corners, chassis-grounded (tie to L2/GND).
- **U1 (WROOM):** antenna at a board edge, **pointing off-board**, with the
  module antenna keepout honored — **no copper on ANY layer under the antenna**
  (including the L2 plane). This is the one keepout that voids the "solid plane".

## Then the four functional clusters (each kept local)

**1. Power front-end / isolation (the heart).** Lay this as one tight cluster:
```
  J1 ──→ C9 ──→ U5(TPS2121 mux) ──→ C_bulk ──→ D1(SS14) ──→ C1(4700µF) + C2 ──→ U3(LP5907) ──→ C3
  (5VSB_RAW)        (IN1)            (+5VSB)    (iso)      (+5V_HOLD reservoir)        (+3V3)
                     ▲
        J6 VBUS ──────┘ (IN2, USB OR-in)   R_ILIM + C_SS at U5
```
- `D1` is the isolation diode: it keeps `C1`'s big reservoir off the measured
  5VSB. Keep `C1`/`C2` on the `+5V_HOLD` side of `D1`; keep `C_bulk`/`C5` on the
  `+5VSB` side. Do **not** bridge them.
- `C1` is the 16 mm 4700 µF can (Panasonic EEVFK1C472M) — it is the biggest part
  on the board; budget its footprint early.
- Blackout sense: `R12/R13` (47k/27k) divide `+5VSB` into U1 GPIO8 — place by
  U1, sensing the rail before `D1`. (On PC power-loss 5VSB collapses → MCU
  dumps from the `+5V_HOLD` reservoir.)

**2. MCU core.** `U1` central. `C4` decoupling at the pin. `SW1`(reset→EN,
with `R2`/`C6`), `SW2`(boot→GPIO0, with `R11`/`C8`), and `U4`(TPS3839
supervisor→EN) clustered at U1. Service/boot are hand-press parts — keep
accessible.

**3. CAN hub.** `U2`(TJA1462A) centered relative to the 4 ports. The **fixed
120 Ω split termination** (`R3`+`R4` = 2×60 Ω, with `C7` 4n7 from `CAN_MID` to
GND) sits **right at U2**. Bus `CAN_H`/`CAN_L` to the 4 ports as a short
multidrop. **No termination at the ports** (Hub-only, locked). CAN control
(`CAN_TX`/`CAN_RX`, U1↔U2) is low-speed — Default class.

**4. DETECT + LEDs.**
- `R5–R8` (10k DETECT pull-ups, **now to +3V3**) each by its port's pin 8;
  `DETECT1–4` to U1 ADC1 channels. Route `+3V3` to them — microamp current,
  thin trace fine.
- `DL1–DL7` (SK6812 chain) where they need to be seen (top/edge). `LED_DATA`
  U1→DL1, then daisy-chain DOUT→DIN. `+5VSB` to each (firmware current cap, OQ-2).

## Power routing
- **Trunk** (`J1 → U5 → +5VSB star`, ~3 A): **pour it**, or route ≥1.5 mm at
  1 oz. Verify by pour copper area (IPC-2152), not a track floor.
- **Port VCC branches** (`+5VSB` → each RJ-45 pin 1, ~0.5 A each): ≥0.5 mm.
- **`+5V_HOLD`** (post-`D1`, ~0.15 A dump): short, ≥0.5 mm.
- All on the **Power** netclass (1.0 mm default, 0.5 mm DRC floor). GND is poured
  (L2 plane + fills), not a track class.

## Diff pairs (over the L2 GND plane)
- **`USB_DP`/`USB_DM`** (USB FS, 90 Ω): short, coupled, referenced to L2. FS is
  tolerant; recompute width/gap for the final stackup (USB class: 0.2 mm /
  0.13 mm gap is the starting point). CC resistors `R9`/`R10` at J6.
- **`CAN_H`/`CAN_L`**: short + parallel; PCB impedance non-critical (the cable +
  the 120 Ω split are the controlled medium).

## Keepouts
- **WROOM antenna** — no copper, any layer (breaks the L2 plane locally).
- Nothing else special; <=5 V everywhere, 0.2 mm clearance is ample.

## Netclasses / DRU (already in the project)
| Class | Nets | Intent |
|---|---|---|
| **Power** | `+5VSB`, `5VSB_RAW`, `+5V_HOLD`, `USB_VBUS` | 1.0 mm default; trunk poured/≥1.5 mm; 0.5 mm DRC floor |
| **USB** | `USB_DP`, `USB_DM` | 90 Ω FS pair; 0.1–0.2 mm gap rule; recompute for stackup |
| **CAN** | `CAN_H`, `CAN_L` | coupled + short; stock diff fine |
| **Default** | `+3V3`, `GND`, `DETECT1–4`, `LED_DATA`, `CAN_TX/RX/MID`, `EN`, `GPIO0`, `USB_CC1/2`, control | autorouter/Quilter OK |

## The Quilter / autorouter split
This board is simple enough to mostly hand-route, or to delegate after locking:
the connectors + the **power front-end cluster** + the **antenna keepout** + the
**USB/CAN diff pairs** (lock these), then let the router handle the digital web
(DETECT, control GPIO, LED data, +3V3 distribution) and the ground/copper fill.
