# USB-ingress BOM delta — the v1.6.0 backfeed-protection package (2026-07-24)

**What this is.** The per-board part plan for spec v1.6.0 (USB-backfeed protection package;
owner rulings 2026-07-24, sign-off record `docs/owner-queue.md` 2026-07-24 rows; spec
sections 2.9 / 6.14 / §11 v1.6.0 entry). The generated `bom/*.csv` files are **not** edited
here — they regenerate from the schematics. This document is the input contract for the
schematic implementation pass (Sonnet, via MCP): refdes plan, part identities, net moves,
and the strap-value derivations. Refdes proposals were checked free against each board's
current BOM on 2026-07-24; the implementing pass owns final refdes assignment if a
collision has appeared since.

**Scope.** Beta line only (alpha + ordered rev2 frozen as shipped): `beta/atx-24pin-rev3`,
`beta/eps-8pin`, `beta/pcie-8pin-2port`, `beta/pcie-8pin-3port`, `beta/12vhpwr-standard`,
`beta/hub-standard-rev2`. `beta/eps-8pin-rev3` (owner-gated) inherits the EPS delta
verbatim if/when un-gated. **`beta/argb-standard` is explicitly NOT in the class** — its
logic-power OR is a true three-way per-source diode-OR (D2 `+5V_LED` / D3 `+5VSB_RJ` /
D4 `VBUS`, one SS34 per source, `05-mcu` sheet), so VBUS is already reverse-isolated from
every other source leg; no change.

---

## 1. Shared part set (verified 2026-07-24)

| Part | MPN | LCSC | Package | Status / provenance |
|---|---|---|---|---|
| Priority power mux | TPS2121RUXR (TI) | **C485916** | VQFN-HR-12 (RUX) | Reuse — already sourced on hub-standard (U5/U7) and atx-24pin-rev3 (U5). Stock verified 2026-07-24: **3,473**; ladder $1.1633@1 / $1.0299@10 / $0.8135@100 / $0.7566@1000. Extended. |
| VBUS polyfuse (modules) | 1206L075/16WR (Littelfuse) | **C371166** | 1206 | NEW platform line. 750 mA hold / 1.5 A trip / 16 V / 100 A max. Stock verified 2026-07-24: **7,735**; ~$0.23@5 (LCSC). Extended. 16 V rating chosen over the hub's 6 V F1–F4 family (C46640983) deliberately: this fuse must survive a faulted-PSU overvoltage appearing across a failed mux (quality-first ruling). |
| KVM polyfuse (hub) | FSMD110-16-1206R (FUZETEC) | **C5707763** | 1206 | NEW platform line. 1.1 A hold / 2.2 A trip / 16 V. Stock verified 2026-07-24: **1,015** (thin — restock watch); $0.1082@5. Extended. Fallback: Littelfuse 1206L110/16WR (not LCSC-carried; DigiKey ~7.9k, consign). The 6 V Littelfuse 1206L110SLYR (C2153847) was REJECTED: out of stock and under-voltage-rated. |
| C_SS soft-start 2.2 µF | CL10A225KO8NNNC (Samsung) | **C23630** | 0603 | Reuse — the hub's C_SS1/C_SS2 line (hub-proven ~10 ms ramp). New line on the module BOMs (same 0603 land as their C15849 1 µF line). Basic-class MLCC. |
| ILIM strap 100 kΩ 1% | 0402WGF1003TCE (UNI-ROYAL) | **C25741** | 0402 | Reuse — already a line on every module BOM (R7) and the alpha hub (R29/R30). Basic. |
| OV1 divider top 47 kΩ 1% | 0402WGF4702TCE (UNI-ROYAL) | **C25792** | 0402 | Reuse — hub line (R12/R15/…); NEW line on module BOMs (their only 47 k today is the 12VHPWR's 0.1% Yageo R5, not needed here — 1% is fine for a ±5% comparator). Basic. |
| OV1 divider bottom 10 kΩ 1% | 0402WGF1002TCE (UNI-ROYAL) | **C25744** | 0402 | Reuse — already on every board (R2 etc.). Basic. |
| PR1 divider 100 kΩ / 33 kΩ 1% | 0402WGF1003TCE / 0402WGF3302TCE | **C25741 / C25779** | 0402 | 100 k reused as above; 33 k = the 24-pin rev3's own U5 PR1 divider value (R53, currently LCSC-blank in its BOM — back-annotate C25779 at the same pass; verified in stock, JLC-carried). Basic. |
| Mux input bypass 100 nF | CL05B104KO5NNNC (Samsung) | **C1525** | 0402 | Reuse — on every board. Basic. |
| Mux input bulk 10 µF | CL21A106KAYNNNE (Samsung) | **C15850** | 0805 | Reuse — on every module (C6/C7/C9). Hub uses its 0603 10 µF line C96446. Basic. |
| DELETED per module | SS34 (D2) | C8678 | SMA | The retired ORing Schottky. 12VHPWR: delete **D2 only** — D5 (SS34 fan flyback) stays. ARGB keeps all three of its per-source SS34s. |

## 2. Strap-value derivations (TPS2121 datasheet SLVSEA3, verified against its own tables)

**Pin map (RUX-12):** 1/8 = OUT, 2 = IN2, 3 = CP2, 4 = OV2, 5 = OV1, 6 = PR1, 7 = IN1,
9 = ST, 10 = ILIM, 11 = SS, 12 = GND. OV1/OV2/PR1/CP2/ST: "connect to GND if not
required." Abs max IN/OUT 24 V; OV/PR pins 6 V; internal comparator reference
V_REF = 1.01/1.06/1.10 V (min/typ/max, rising).

**ILIM (~1 A class, owner ruling).** Datasheet law: **I_LIM = 65.2 / R_ILIM^0.861**
(R in kΩ, I in A). Validation against the datasheet's own electrical table:
44.2 kΩ → 65.2/26.1 = **2.50 A** (table: 2.5 A typ); 80 kΩ → 65.2/43.5 = **1.50 A**
(table: 1.5 A typ, 1.0–2.0 min–max). Cross-checks against the fleet: hub R_ILIM1/2 =
27 kΩ → **3.8 A**; 24-pin U5 R50 = 20 kΩ → **4.9 A**. For the ruled ~1 A: the exact
solve is R = (65.2/1.00)^(1/0.861) ≈ **128 kΩ — outside the datasheet's recommended
R_ILM window of 18–100 kΩ**, so the spec value is the in-range, already-sourced
**100 kΩ → I_LIM = 65.2/100^0.861 = 65.2/52.6 ≈ 1.24 A typical** (scaling the 80 kΩ
row's ±33% band: ≈ 0.8–1.65 A limits). Above the ESP32 flash-burst ~500 mA; ~1 A-class
per the ruling; tolerance is irrelevant to safety because isolation, not the limiter,
is the load-bearing mitigation (owner ILIM ruling) and the 750 mA-hold polyfuse is the
host-protection element.

**Soft start.** C_SS = 2.2 µF, the hub-proven value (~10 ms output ramp). Module local
bulk (≈ 30–50 µF post-mux) charges at ≈ C·dV/dt ≈ 25–50 mA — three orders under any
port limit (the owner row's ~50 mA figure).

**OV1 (~6 V faulty-PSU cutoff, PSU-side input).** Divider from IN1 to GND, tap at OV1;
the input disconnects when V_OV1 > V_REF. With 47 kΩ / 10 kΩ:
**V_cut = 1.06 × (47+10)/10 = 6.04 V typical**; worst-case band ≈ **5.70–6.33 V**
(V_REF 1.01–1.10 plus ±1% resistors). Sits above ATX 5VSB max (~5.25 V) and USB VBUS
max (5.5 V), below the LP5907 input abs-max (6.5 V); the mux itself is a 22 V part and
survives the insult while disconnecting the load. Divider burden 5 V/57 k ≈ 88 µA
(OV pin leakage ±0.1 µA — negligible error). At a 22 V insult the OV pin sees
22×10/57 = 3.86 V < the pin's 5.5 V recommended max — the divider also keeps the pin
itself safe.

**PR1 (priority-valid threshold, PSU-side input).** 100 kΩ / 33 kΩ from IN1 (the
24-pin U5's proven R52/R53 values): IN1 is treated valid while
V_IN1 > 1.06 × 133/33 = **4.27 V typ** — the stage falls back to USB below a sagging
~4.3 V PSU rail. On the hub's new U11, mirror the as-built U5/U7 PR1 strap style (the
implementing pass reads it off the hub schematic); if a divider, use the same
100 k/33 k. CP2, OV2 (and OV1 where unused), and ST strap to GND per the pin table;
an ST readout to a spare GPIO (10 kΩ pull-up, C25744) is optional and
pin-budget-permitting, matching the 24-pin's existing MUX_ST net.

## 3. Per-board deltas

Wiring order at every module USB entry (per §6.14 posture): connector → ESD clamp
(existing) → **F1 polyfuse (new)** → FB1 VBUS bead (existing) → mux IN2. PSU-side
entry: existing port bead/tap → mux IN1. Existing rail bulk (C6/C7/C9 class) stays on
the rail net, which becomes the soft-started mux OUT.

### 3.1 eps-8pin (also the template for eps-8pin-rev3 when un-gated)

| Action | Refdes | Part / value | LCSC | Role |
|---|---|---|---|---|
| ADD | U4 | TPS2121RUXR | C485916 | USB ingress mux. IN1 (pin 7) = RJ-45 VCC feed (J1.1 → FB2 → IN1); IN2 (pin 2) = VBUS via F1/FB1; OUT (1,8) = +5VSB logic rail |
| ADD | F1 | 1206L075/16WR, 750 mA/16 V | C371166 | VBUS polyfuse, ahead of the mux (layer 2) |
| ADD | R13 | 100 kΩ 0402 1% | C25741 | ILIM strap → ~1.24 A typ |
| ADD | R14, R15 | 47 kΩ / 10 kΩ 0402 1% | C25792 / C25744 | OV1 divider from IN1 → ~6.04 V cutoff |
| ADD | R16, R17 | 100 kΩ / 33 kΩ 0402 1% | C25741 / C25779 | PR1 divider from IN1 → ~4.27 V validity |
| ADD | C41 | 2.2 µF 0603 | C23630 | C_SS soft start |
| ADD | C42 | 100 nF 0402 | C1525 | IN2 (VBUS) bypass at pin 2 |
| ADD | C43 | 10 µF 0805 | C15850 | IN2 (VBUS) bulk |
| DELETE | D2 | SS34 | C8678 | Retired ORing Schottky |
| STRAP | — | CP2, OV2, ST → GND | — | Per datasheet pin table |

Note: EPS carries no discrete VBUS PESD (its splice relies on the USBLC6's own VBUS
clamp, recorded §6.14) — unchanged by this delta; the OQ-83 reconciliation pass decides
that separately.

### 3.2 pcie-8pin-2port and pcie-8pin-3port

Identical to the EPS delta (same refdes plan: U4, F1, R13–R17, C41–C43, delete D2;
both boards' R13+/C41+ verified free). Their discrete VBUS clamp D4 (PESD5V0S1BA)
stays at the connector, ahead of F1.

### 3.3 12vhpwr-standard

Same shape, shifted refdes (U4 = REF3030, C24, R22/R23 are taken):

| Action | Refdes | Part / value | LCSC | Role |
|---|---|---|---|---|
| ADD | U5 | TPS2121RUXR | C485916 | USB ingress mux (U5–U9 free; INA240s are U10–U15). IN1 = RJ-45 VCC feed; IN2 = VBUS via F1/FB1; OUT = +5VSB rail |
| ADD | F1 | 1206L075/16WR | C371166 | VBUS polyfuse |
| ADD | R24 | 100 kΩ 0402 | C25741 | ILIM strap |
| ADD | R25, R26 | 47 kΩ / 10 kΩ 0402 | C25792 / C25744 | OV1 divider (1% UNI-ROYAL — NOT the 0.1% Yageo R5/R6 precision line) |
| ADD | R27, R28 | 100 kΩ / 33 kΩ 0402 | C25741 / C25779 | PR1 divider |
| ADD | C25, C26, C27 | 2.2 µF / 100 nF / 10 µF | C23630 / C1525 / C15850 | C_SS; IN2 bypass; IN2 bulk |
| DELETE | D2 | SS34 | C8678 | **D2 only** — D5 (SS34 fan flyback on J2) STAYS |

### 3.4 atx-24pin-rev3

The 24-pin already muxes MAIN_5V × 5VSB (U5, with R50 ILIM 20 k / R52+R53 PR1
100 k/33 k / C50 SS 2.2 µF). The new stage inserts **in the 5VSB leg**, exactly per the
owner text ("VBUS + the module's 5VSB source as mux inputs") and hub-parity
(5VSB>USB stage feeding the MAIN stage): total priority MAIN_5V > 5VSB > USB.

| Action | Refdes | Part / value | LCSC | Role |
|---|---|---|---|---|
| ADD | U6 | TPS2121RUXR | C485916 | IN1 = post-shunt +5VSB tap (the net feeding U5 pin 2 today); IN2 = VBUS via F1/FB1; OUT → U5.IN2 (net move) |
| ADD | F1 | 1206L075/16WR | C371166 | VBUS polyfuse (D3 PESD clamp + FB1 bead stay; order: J5 → D3 → F1 → FB1 → U6.IN2) |
| ADD | R54 | 100 kΩ 0402 | C25741 | U6 ILIM strap |
| ADD | R55, R56 | 47 kΩ / 10 kΩ 0402 | C25792 / C25744 | U6 OV1 divider from the 5VSB tap → ~6.04 V faulty-PSU cutoff |
| ADD | R57, R58 | 100 kΩ / 33 kΩ 0402 | C25741 / C25779 | U6 PR1 divider (mirrors U5's R52/R53) |
| ADD | C51, C52, C53 | 2.2 µF / 100 nF / 10 µF | C23630 / C1525 / C15850 | U6 C_SS; IN2 bypass; IN2 bulk |
| DELETE | D2 | SS34 | C8678 | Retired ORing Schottky |
| ANNOTATE | C50, R53 | 2.2 µF / 33 kΩ | C23630 / C25779 | Back-fill the LCSC-blank existing U5 support lines with the same platform parts |

Beyond-package recommendation (flag for owner at the schematic pass, NOT ratified):
OV1/OV2 dividers on U5's own MAIN_5V/5VSB inputs would move the ~6 V disconnect to the
PSU-facing stage as well; the ratified package protects the logic rail via U6 alone.

### 3.5 hub-standard-rev2 (KVM third stage)

| Action | Refdes | Part / value | LCSC | Role |
|---|---|---|---|---|
| ADD | U11 | TPS2121RUXR | C485916 | Third cascade stage (U9/U10 left reserved for the alpha H2 rung-3 DNP convention). IN1 = /PSU_5V (U5.OUT); IN2 = /KVM_5V_IN via F5; OUT = new net → U7.IN2 |
| ADD | F5 | FSMD110-16-1206R, 1.1 A/16 V | C5707763 | KVM 5 V polyfuse (F1–F4 are the 2026-07-15 per-port 500 mA PTCs) |
| ADD | R_ILIM3 | 27 kΩ 0402 | C25771 | ILIM strap, mirrors the shipped stages (~3.8 A; the F5 polyfuse is the tighter element toward the wall-wart) |
| ADD | C_SS3 | 2.2 µF 0603 | C23630 | Soft start, hub-proven value |
| ADD | C22, C23 | 100 nF 0402 / 10 µF 0603 | C1525 / C96446 | U11 IN2 bypass/bulk (hub's own 0603 10 µF line) |
| NET MOVE | J_KVM pin 1 | +5VSB → /KVM_5V_IN | — | The raw rail tap is retired; the pin becomes inbound-only (spec §2.9/§4 v1.6.0). D7 (PESD on the 3V3 ref pin) unchanged |
| NET MOVE | U7 pin 2 (IN2) | /PSU_5V → U11.OUT | — | Completes MAIN_5V > 5VSB > USB > KVM |
| STRAP | — | U11 PR1/CP2/OV1/OV2/ST | — | Mirror the as-built U5/U7 strap style; 100 k/33 k (C25741/C25779) if a PR1 divider is used — note the rev2 BOM carries no 100 k line today, so that would be a new line |

## 4. Cost delta (100-qty class)

Per module: TPS2121 $0.81 + polyfuse ~$0.15 + straps/caps ~$0.05 − SS34 ~$0.02 ≈
**+$1.0/board**. Hub: ≈ **+$1.0** (mux + 1.1 A polyfuse + straps). Recorded in spec §9
(table figures unchanged as printed; quality-first ruling governs).

## 5. First-article bench gate (carried from the ruling — do not drop at implementation)

TPS2121 **unpowered reverse behavior**: OUT driven at 5 V with BOTH inputs dead,
module topology and KVM topology. The datasheet's reverse-current blocking
(0.2/1/2 A detection, 10 µs) is characterized for a live device only. Load-bearing for
(a) host plugged into a fully dead module+PSU, (b) wall-wart into a dead hub. Until
measured, the interim bench rules of spec §2.9 v1.6.0 stand.
