# 24-pin ↔ host-PC USB fault-coupling study — can a faulty PSU trip the PC port? (2026-07-24)

**Question (owner, 2026-07-24):** across the latest revisions on all branches of the
"24-pin tester", could a faulty PSU cause the USB out of the 24-pin to trip overcurrent
or overvoltage on the PC it is plugged into — e.g. bulk-cap discharge?

**Scope surveyed (branch sweep, 2026-07-24):** the "24-pin tester" resolves to two
artifacts, both examined: (a) the **atx-24pin module** used as the bench PSU-tester
front-end (rev3 carries the owner-ruled 2026-07-14 ATX control block + BENCH-TESTER-MODE;
its USB-C **is** "the USB out of the 24-pin"); (b) the **ST tester** (`testers/
tester-standard/`, sheets 01–05e), which rides the module for T1/T3/T6 + power-cycling
and whose own USB-C is PD self-power + the ratified USB-direct fallback link. Revisions:

| Artifact | Latest state | Where |
|---|---|---|
| atx-24pin alpha | D1 diode-OR direct onto `+5VSB` busbar, no USB protection suite | `modules/atx-24pin/` (main) |
| atx-24pin rev2 (ordered hw) | same topology as alpha (+ known J1.1 RJ-45 VCC parallel path) | `modules/atx-24pin-rev2/` (main) |
| atx-24pin rev3 BETA-2 | TPS2121 mux + D2 + full H3/H3a USB suite | `modules/atx-24pin-rev3/` (main = pr50 head 24d170ab) |
| atx-24pin rev3 beta line | **identical USB/power topology**; only J6→J6P/J6C/J6D mezz split | `beta/atx-24pin-rev3/` (origin/claude/pipeline-pass-2, ff5d405e/acf03d12, 2026-07-22 — newest anywhere) |
| ST tester sheets 01/02 | RJ-45 mis-plug chain + USB-C PD (CH224K→dual TPS54331) | `testers/tester-standard/` (identical on main / pr50 / pipeline-pass-2) |

All connectivity claims below are **netlist-verified** (`kicad-cli sch export netlist`,
KiCad 10.0.4) — not read off the drawing.

## 1. Verdict, short form

1. **Overvoltage out to the PC: NO single-fault path, on any revision.** The USB-VBUS
   ORing diode is oriented anode-on-VBUS / cathode-on-board-rail on every revision
   (alpha/rev2 `D1`, rev3 `D2` SS34, 40 V reverse) — a PSU rail fault (5VSB high, even a
   12V-into-5VSB internal short) reverse-biases it. Rev3 adds the TPS2121 whose inputs
   are rated to 22 V and whose reverse-current blocking is always-on, plus D7
   (PESD5V0S1BA, 5 V stand-off) clamping `VBUS_RAW`. A gross 5VSB OV kills module parts
   (LP5907 abs-max ≈6 V, TJA1051 VCC) but the port never sees it. Residual = double
   fault (D2 failed short **and** PSU OV) — not a design gap at this tier.
2. **Literal "bulk-cap discharge into the PC": no path.** PSU-side stored energy cannot
   reach VBUS through a reverse-biased Schottky; on rev3 the mux RCB additionally
   isolates both PSU inputs. The only constructed discharge path is a board-level short
   of −12 V onto the VBUS domain (e.g. a bridged `J_SIG1` stub, 2.54 mm pitch, −12 V
   adjacent to PS_ON#/PWR_OK) — D2 then conducts the *PC* into the −12 V rail → port
   OCP trip. Mechanical double-fault; noted, not actionable at schematic level.
3. **Overcurrent trip at the PC port: YES — real, but in the reverse direction.** The
   PSU never pushes current into the port; the port gets *pulled from*. Any 5VSB
   collapse with USB attached (dead PSU, hiccup-mode protection cycling, standby
   drooping under cross-load, an SCP/OCP test leg collapsing 5VSB, or simply AC-off)
   makes the PC the fallback source through the ORing diode. Whether the port trips is
   purely a question of what hangs downstream — see §3. **This is the scenario behind
   the question, and it is config-dependent, not hypothetical.**
4. **ST tester's own USB-C: no DUT copper coupling at all** (verified: `VBUS_C` touches
   only CH224K/USBLC6/bucks; DUT rails terminate in the load slices). Exposure is
   common-ground only — **but two real capture bugs were found in `02-power`** (§5):
   U5 (USBLC6-2SC6) physically shorts D+↔CC2 and D−↔CC1 through its internally-tied
   flow-through pins, and U5's VBUS pin (5.25 V rating) sits on the PD-negotiated
   12/20 V rail. As captured, PD negotiation cooks U5 and the ratified USB-direct
   fallback link cannot enumerate. Not caught by the 2026-07-16 pin audit (no U5 rows).

## 2. As-built topology per revision (netlist facts)

**alpha / rev2** (`modules/atx-24pin{,-rev2}`): net `+5VSB` = J3.9 (PSU) + **J1.1
(RJ-45 VCC)** + **J2.1 (TO-HUB-PWR JST)** + RS6 25 mΩ (→ J4/output busbar) + LDO + CAN
VCC + D1 cathode; D1 anode = J5 VBUS (+C15 10 µF). No USBLC6, no VBUS clamp/bead, no
mux; CC 5.1k pulldowns present. USB is diode-OR'd **directly onto the PSU standby
node**.

**rev3 BETA-2** (`modules/atx-24pin-rev3`, identical in `beta/` on pipeline-pass-2):
- `+5V_SYS` (module logic rail) = U5 TPS2121 OUT ‖ D2(SS34) cathode; sources: IN1 =
  `+5V_MAIN` (post-RS2 main-5V tap, TB2/TB3 node), IN2 = `+5VSB` (J3.9, pre-RS4), D2
  anode = `VBUS` (J5 → FB1 MPZ2012 bead → C9 10 µF). PR1 = 100k/33k from IN1 → main-5V
  priority engages ≈4.3 V (the §2.9 MAIN_5V > 5VSB > USB ladder, on-module).
- ILIM R50 = 20 kΩ → I_LIM = 65.2/20^0.861 ≈ **4.9 A** (mux legs only — **the D2/USB
  leg bypasses ILIM entirely**); transient OCP 2.4×; RCB always-on per channel; OV1/OV2
  = GND (input-OV supervisor disabled; inputs rated 2.8–22 V) [TPS2121 ds §9.3.2/9.3.6].
- `+5V_SYS` → FB2 (0R) → `/+5V_SYS_PORT` → **J2 JST + J6P mezz pins 1/3/5** (the Hub
  bulk feed). H3/H3a suite: D_USB1 USBLC6-2SC6 on D±, D7 PESD5V0S1BA on `VBUS_RAW`,
  CC 5.1k, SBU n/c. The 5VSB *pass-through* busbar (J3.9 → RS4 → TB5 blade → DUT loads/
  daughterboard) never touches `+5V_SYS` except through the mux (RCB) — so USB-side
  back-feed can reach **neither the PSU nor the output/motherboard side** on rev3.

## 3. The overcurrent scenarios, quantified

PC port budgets: 500 mA (USB2) / 900 mA (USB3) / 1.5–3 A (charging ports); polyfuse
ports sag-and-trip thermally (seconds), eFuse ports latch in ms. Module standalone draw
(ESP32-C6 + 4×INA238 + TJA1051 idle, no LED chain on this board) ≈ 100–150 mA class.

| Config with USB attached, 5VSB collapses | What the PC port picks up | Trip? |
|---|---|---|
| rev3 module alone (bench self-test) | module logic only | **No** — comfortably inside even 500 mA |
| rev3 module + Hub on J2/J6P (+5V_SYS feed) | module + Hub Standard + Hub's per-port RJ-45 VCC fleet + LED chains (OQ-2 tree budget ≈2.5 A) | **Yes** on 0.5/0.9 A ports; marginal even on charging ports. SS34 3 A rating is adjacent — a hub tree near budget also cooks D2 (1.2 W in SMA) on a port dumb enough to supply it |
| rev2/alpha module, PSU connected but dead/off | above **plus** the PSU's own 5VSB output caps (mF-class inrush) **plus**, if cabled, the motherboard's standby domain via J4 | **Yes** — near-certain in-system; bench-only still takes an mF-class inrush hit at every collapse |
| hiccup-mode faulty PSU (protection cycling ~Hz) | repetitive full-load bursts as D2 alternately conducts | polyfuse heating → delayed trip; eFuse ports latch on the first heavy burst |
| ST deck (§12b): hub bay fed from module **blades** (raw 5VSB per sketch L841/868) | hub loses its feed on collapse and swaps to **its own** USB input | trip exposure moves to the **Hub's** PC port (same tree arithmetic; Hub mux ILIM bounds it) |

Attach inrush (PSU absent): C9 10 µF + ~34 µF behind D2 (C25 22µ + C6 10µ + C1 1µ) ≈
44 µF vs the USB 10 µF attach spec — over-spec but universally tolerated; not a trip
mechanism. With the PSU alive, D2 is reverse-held and attach presents C9 only.

**Why this is genuinely "faulty-PSU-caused":** the module's standalone/§6.14 posture
*intends* USB to take over when standby dies — that is the feature. The fault coupling
is that the PC port inherits whatever standby tree the module is feeding at that
moment, and a faulty PSU (droop, hiccup, 5VSB short) is exactly what forces the
handoff, repeatedly. The design correctly confines this to current the *port* can
refuse (OCP), never voltage the port must absorb.

## 4. Ground-path caveats (not port OCP/OVP, but same bench)

- A PSU primary-secondary insulation fault or heavy leakage puts DUT secondary at
  line-referenced potential; the USB cable is then the fault's path to the PC's PE.
  Shop guidance for suspect units: isolated USB (ADuM-class) or link via the Hub, and
  the deck's planned overflow **USB hub must be SELF-POWERED** (sketch §13-overflow) so
  the PC port carries data only.
- ST-deck SCP/crowbar legs run on DUT stored energy (sketch §3b); keep bank return
  copper out of the module/USB ground path (single-point tie) when the slot-deck board
  is laid out — a shared-return IR shift during a crowbar rides the USB ground into
  the PC. Layout requirement, deck copper not yet drawn (08-deck-io held).

## 5. New defect found (ST tester `02-power`, committed 3e3a2a2d line)

`U5` USBLC6-2SC6: pin 1 (I/O1) → `USB_D_P`, pin 6 (**same internal node** — flow-through
part, both pins named I/O1, ST ds) → `USB_CC2`; pin 3 (I/O2) → `USB_D_N`, pin 4 (tied)
→ `USB_CC1`. As wired the part **shorts D+↔CC2 and D−↔CC1**. ERC-invisible (the
netlist sees four distinct pins). Additionally U5 pin 5 (VBUS, I_RM spec'd at
V_RM = 5.25 V) sits on `VBUS_C`, which CH224K negotiates to 12/20 V PD — over the
part's rating; its internal VBUS clamp will conduct/fail on the first PD contract.
Consequences: PD brick mode degrades/destroys U5; USB-direct-to-PC fallback (ratified
§12b fallback) cannot enumerate (D− loaded by CC1's 5.1k Rd + CH224K PHY). Fix shape
(for the held tester continuation agent, owner-gated resume): U5 → D± only (1,6 = D_P
in/out; 3,4 = D_N — the Hub/module reference pattern), CC ESD via discrete PESD-class
low-cap clamps if wanted, and VBUS-side protection by a ≥24 V-tolerant TVS (SMAJ-class),
not USBLC6. Logged in FOLLOWUPS.md; **not** fixed in this pass (sheets are the held
agent's WIP; owner said hold).

## 6. Recommendations (proposals only — nothing implemented)

1. **OQ-85 interlock row (firmware, tester program):** when running VBUS-powered
   (mux ST pin already exposes source state on `/MUX_ST`), refuse or warn on test legs
   that intentionally collapse 5VSB while a Hub tree hangs on `/+5V_SYS_PORT`; report
   "USB budget exceeded" instead of brown-outing the PC port. Zero hardware.
2. **Deck spec line (slot-deck README when 08-deck-io lands):** overflow USB hub =
   self-powered, powered from tester logic rails; never bus-powered from the shop PC.
3. **Owner decision (optional, beta-line hardware):** whether the module's D2 leg gets
   a current bound of its own (PTC ~0.75 A hold, or a current-limited load switch) so a
   collapsing PSU can never drag a generous host port to its trip point through us.
   Costs a diode-drop's worth of board area; the platform posture to date accepts
   port-OCP as the backstop (Hub §2.7 does the same). Queued in docs/owner-queue.md §1.
4. rev2/alpha field note (consumer disclosure ladder, D-8): with a system installed on
   a rev2 board, "PC USB attached + PSU switched off" back-feeds the board's standby
   tree from the PC port until the port trips — harmless to the PSU, annoying to the
   user, absent on rev3.

## 7. Provenance

Netlists exported 2026-07-24 from: `modules/atx-24pin{,-rev2,-rev3}` @ main 24d170ab,
`beta/atx-24pin-rev3` @ origin/claude/pipeline-pass-2, `testers/tester-standard/
02-power.kicad_sch` @ main. Datasheets: TPS2121 (vendored, SLVSEA3F — ILIM eq p13, RCB
§9.3.6, 22 V table p6), LP5907 (vendored, abs-max p4), USBLC6-2 (ST, fetched — I/O
flow-through pin pairs p1, V_RM 5.25 V p2). Prior rulings honored: sense-wire study
2026-07-14 §7/§8 (host-attached refusal), §12b dock ratification, H3/H3a suite
(beta-splices/atx-24pin.md). This study adds the USB-port fault-coupling analysis
neither document covered.
