# PSU tester — architecture sketches (componentry, speed, cooling, form, data, timing)

SKETCH (2026-07-16, owner-requested). Builds on: canonical
`docs/psu-tester-exploration-2026-07-14.md` (+§6 tier ruling),
`docs/psu-tester-component-research-2026-07-16.md` (part classes + prior art).
Numbers carried from those docs are settled; numbers introduced here are
SKETCH-ESTIMATES marked (~) and get frozen at schematic time.

## 0. Two principles that shape everything

1. **The tester is an actuator, not an instrument.** Measurement truth lives
   in the CEC modules sitting inline (their existing cal story, ±0.5–1 %).
   The tester's own sensing is control-loop + safety grade (~1–2 %), which
   collapses its precision burden: no cal lab, no drift spec, no premium
   shunts outside the loops.
2. **Heat is the product.** Every tested watt becomes tester heat on purpose.
   The chassis is designed around the airflow path first; electronics fit
   into the cool zone that layout leaves.

## 1. System block + power domains

```
                        BENCH TOP
  PSU-under-test ──24-pin──▶ [24-pin module]──ext──▶┐
        │        ──EPS×2──▶ [EPS module]────ext──▶│  TESTER FRONT BAY
        │        ──PCIe×2/3▶ [PCIe module]──ext──▶│  (fixture heads on a
        │        ──12V-2x6─▶ [12VHPWR mod]──ext──▶│   replaceable plate)
        │                        ▲ modules click into the MODULE DECK (lid rail)
        │
  CAN bus (RJ-45 daisy): Hub ◀──▶ modules ◀──▶ TESTER-MCU (one more CAN module)
  Host PC: Hub USB (fleet telemetry) + tester USB-C (service / Max waveforms)
```

**Power domains (important, easy to get wrong):**
- DUT domain: the PSU under test powers the Hub + modules exactly as in a PC
  (24-pin module 5VSB feed → Hub JST → module VCC) — that IS part of the test.
- Tester domain: brains, fans, gate rails, DACs run from the tester's **own
  external 12 V brick** (~2–3 A). The DUT must never power the thing loading
  it (a dying DUT would brown out its own executioner mid-record).
- Commons: one **star ground at the load return bus** (heavy copper/bus bar);
  control grounds tie at that single point. Load returns NEVER share a trace
  with sense/control returns (the platform's Kelvin doctrine, scaled up).

## 2. The repeated unit — one load channel slice

```
from fixture head ──▶ heavy bus ──┬─▶ [R-bank leg ×N]  R(100 W alu-shell) ── NFET sw ── fuse ─▶ RETURN
                                  ├─▶ [vernier]  L2 FET ── ballast R ── Kelvin shunt ─▶ RETURN
                                  │       ▲ gate ◀── CC op-amp ◀── DAC ref (DAC80508 ch)
                                  │       ├ per-device NTC → MCU
                                  │       └ gate pull-down + de-gate rail (watchdog, default = NO LOAD)
                                  └─▶ [§6.13 trip watch]  INA181 + TLV7011 → MCU capture (µs)
```

Channel plan (canonical): 12V-2x6 600 W/50 A, EPS 2×300 W, PCIe 2–3×150 W,
24-pin group (12 V ~10 A, 5 V 20 A, 3.3 V 20 A, 5VSB 3.5 A, −12 V 0.3 A
switched-R only). ~8 CC loops total = one DAC80508. R-bank granularity (~):
binary-ish steps per big channel (e.g., 12 V legs of 2/4/8/16 A class), the
vernier (one L2 device per big channel, ~100–150 W each) fills between steps
and does ramps/corners.

**The fast excursion channel (ONE, Pro and Max; Max adds a switch matrix to
point it at EPS too):** AN133-descended slice living ON the 12V-2x6 fixture
block (mm-scale bus — µH costs 5 V at 5 A/µs):

```
level DAC ─▶ [analog slew shaper ≤5 A/µs, settable 2.5] ─▶ fast CC loop (OPA810-class + gate stage)
MCU GPTimer gate (µs) ─▶ pulse trains 100 µs/1 ms/10 ms/100 ms @ Table 3-3 duty
FETs: 3–4× L2, ballasted, sized by 100 µs pulse SOA (~90–100 A pulses)
its own Kelvin shunt + fast comparator → µs "pulse-actual" stamp
```

## 3. Speed budget (how fast each piece honestly needs to be)

| Subsystem | Requirement | Source/derivation |
|---|---|---|
| Fast channel slew | ≤5 A/µs (settable 2.5) — shaped analog, never software | ATX 3.1 Table 4-4 / canonical §3c |
| Fast channel loop BW | ~500 kHz (flat-top settle ≪100 µs pulse; edges ~18 µs at 90 A) | canonical §3c; AN133 practice |
| Fast pulse timing | 1 µs gate resolution; trains to 100 ms | Table 3-3; any GPTimer |
| Dynamic step tests | 50 Hz–10 kHz repetition, 12 V steps 40–70 % rated → same fast channel; minors 30 % steps @1 A/µs → mid-speed verniers (~100 kHz loop on 5 V/3.3 V) (~) | Table 4-3/4-4 |
| Vernier loops (bulk) | ~10 kHz BW — cross-load corners, OCP ramps | ms-class events |
| R-bank switching | ms class (FET on/off; no slew requirement — steps are “crude but diagnostic”) | canonical §3a |
| Setpoint updates | DAC80508 over SPI, µs-class per write; profiles precompiled step lists | TIDA-01525 pattern |
| Trip timestamping | µs (INA181+TLV7011 → MCU capture) — OCP staircase truth | §6.13 reuse; canonical OQ-11 answer |
| PWR_OK / T-timing | µs edges — measured by the 24-pin MODULE, not the tester | 07-14 sense-wire study |
| Max digitizer | 50–65 MS/s, 1–10 ms windows; AFE 20 MHz; ripple per Table 4-6 | Max lane reuse |
| CAN telemetry | 5 Hz cec_telem + event frames — control plane never carries waveforms | platform pattern |

## 4. Cooling architecture (the big one — designed first)

**Heat split at 1600 W continuous:** R-banks ~1,200–1,300 W; linear FET bank
~300–400 W; electronics <20 W. Excursion trains don't add: spec test keeps
cycle-RMS = rated power, so average dissipation ≈ the continuous budget;
pulses live in the FETs' die mass (pulse SOA), not the sink.

**The airflow path IS the layout (front→back, cold→hot):**

```
FRONT INTAKE ─▶ [electronics + shunts + DAC/MCU  (cool zone, ≤45 °C)]
             ─▶ [linear FET extrusion  (Tsink ≤80 °C target)]
             ─▶ [R-bank DUCT: alu-shell resistors on two facing plates = hot aisle]
             ─▶ REAR EXHAUST (~50 °C at full load, grille + hot-surface label)
```

- **Numbers (canonical Q=ṁcpΔT):** 1600 W @ ΔT_air 20 °C → ~141 CFM real
  delivered → **3–4× 120×25 PWM high-static fans, or 2× 120×38 server class**,
  ducted (open-frame CFM ratings don't survive a resistor tunnel; budget ~2×
  nameplate). 2000 W Max option = +1 fan + longer duct.
- **Linear FET sink (~):** ~400 W on one 300 mm forced-air extrusion needs
  Rθ(sink-air) ~0.1 K/W — big but standard e-load practice (Rigol/Array
  pattern: shared extrusion + fans). Per-device: 100–150 W with Tj ≤125 °C,
  Tcase ≤85 °C (IXTK90N25L2 is rated 690 W @25 °C case — the constraint is
  the sink, never the die).
- **R-bank duct:** alu-shell parts are HAPPY at 150–200 °C internal — the
  duct exists to keep that heat off everything else and off fingers. Chassis
  skin near the duct gets standoff + vents; IEC 62368 touch limits drive the
  grille geometry (canonical §3e).
- **Precision-zone rule:** the tester's loop shunts live in the FRONT cool
  zone (upstream of all heat) — their tempco only pollutes loop accuracy
  (~1–2 % budget, fine), and the real measurement shunts are in the modules
  on the DECK, outside the chassis airflow entirely.
- **Protection ladder (independent layers):** per-device NTC → firmware
  derating curve → watchdog de-gate (gate pull-downs = no-load default);
  fan tach fail → immediate load shed; **plus one dumb bimetal 120 °C
  thermal switch on each plate wired into the de-gate rail** — the analog
  backstop that works with firmware dead.
- **Acoustics:** bench-room posture (canonical): PWM curve keeps <400 W tests
  civil; 1600 W is LOUD and documented as such. Front-counter quiet is a
  non-goal (would double the chassis).

## 5. Form factor — "conveniently bench-able"

**Recommended: bench console, 19-inch-width footprint (~430 × 350 × 150–170 mm,
~8–10 kg), rubber feet, optional rack ears** (~3–4U equivalent — shops with
racks get it for free; benches get a flat-top console).

- **FRONT = the connector bay**: a recessed shelf where the DUT's cables
  land; all fixture heads (the OQ-89 consumable assemblies) mount on **one
  replaceable front plate** — the wear item swaps as a plate, not per-head
  fiddling. Strain bar above the bay; recessed shrouded male headers (stock
  ATX parts are touch-protected by geometry).
- **LID = the module deck**: a rail/tray where the inline modules click in
  (their M3 mounts), so the PSU→module→extension→bay harness dresses flat
  and the modules stay visible (LEDs), cool (upstream of exhaust), and
  strain-relieved. The Hub docks on the same deck; one RJ-45 drop enters the
  tester's CAN port.
- **REAR = all heat + power**: exhaust grille, tester's 12 V brick inlet,
  second CAN RJ-45 (daisy), Max waveform USB-C. NOTHING hot or cabled faces
  the operator.
- **DUT parking**: beside the tester (PSUs vary too much to swallow one);
  optional side tray accessory later. Front-bay cable reach sized for a PSU
  sitting flush left or right (~0.5 m harness envelope).

## 6. Data plane (in and out)

- **Control = CAN, platform-native.** The tester enumerates as one more
  module (DETECT 2.2 kΩ, cec_telem at 5 Hz: per-channel set-vs-actual amps,
  plate temps, fan RPM, fault flags; §6.14 USB-CDC standalone posture free).
- **Profiles are data, compiled host-side:** the bench tool compiles a recipe
  (e.g. "ATX 3.1 suite, 1000 W class") into a step list
  `{t, channel-mask, setpoint, slew-class, expected-window}`; uploads over
  CAN (0x300 command block: PROFILE_LOAD/ARM/START(seq)/ABORT); the tester
  MCU executes autonomously, stamping each step edge (µs, local clock) and
  broadcasting STEP marker frames as it goes. CAN carries **events and
  setpoints only — never waveforms**.
- **Results join host-side:** modules' telemetry + timing captures arrive via
  the Hub as always; the tester contributes its actuation log (step
  timeline + coarse actuals + trip stamps). The report = host joins
  {actuation log × module telemetry × trip/timing events} on the shared
  timebase (§7) against the recipe's expected windows → pass/fail per line →
  customer PDF. Same versioned event-record schema as the platform
  (`firmware/docs/host-data-path-fingerprinting-2026-07-16.md`) — tester
  events land in the same corpus.
- **Max waveforms bypass CAN:** digitizer captures (1–10 ms windows) buffer
  in PSRAM/FPGA and pull over the tester's own USB-HS (P4). The bench tool
  session holds two USB endpoints (Hub + tester) and one merged timeline.

## 7. Cross-timing to the modules (the measurement-truth clock)

The platform already owns the mechanism: a high-priority CAN broadcast is
received by every node within ~1 bit time, and modules already ISR-timestamp
such frames (cec_freeze). Extend, don't invent:

- **CEC_MARK (~0x012, FREEZE-class priority, non-freezing):** payload
  `{origin, seq, origin_µs}`. The tester broadcasts MARK at test start, at
  every step edge, and as a 1 Hz heartbeat during long tests. Every module's
  CAN ISR stamps arrival on its local µs clock (the existing cec_freeze hook
  generalized to a mark table).
- **Host clock-fusion:** per node, fit `t_module = a + b·t_tester` over the
  mark series (the 1 Hz heartbeat carries drift: ESP32 XOs are ±10–20 ppm →
  ~6–12 ms/10 min if uncorrected — hence continuous marks, not one-shot
  sync). All telemetry/captures re-based onto the test timeline in software.
- **Alignment budget:** ~±(1 CAN bit + ISR jitter) ≈ **±2–10 µs** at 500 k
  (~±10–20 µs even at the 125 k bench rate) — 100× tighter than the ms-class
  ATX timing tests need, and tight enough to bracket 100 µs excursion pulses
  against the modules' §6.13 comparator stamps.
- **The excursion cross-time chain, concretely:** tester gate stamp (µs) →
  module comparator trip stamp (µs, §6.13) → [Max] digitizer waveform
  (sample-exact within its own capture, capture-start MARK-referenced). The
  modules' 1 kHz INA rings bracket the envelope; FREEZE co-capture still
  works system-wide if a test trips a module's own detector — the tester is
  just another FREEZE participant.
- **PWR_OK/T1/T3/T6:** measured µs-grade by the 24-pin module on the same
  timeline; the tester's PS_ON# assert is itself a MARKed step. Hold-up
  (Max): the AC interrupter reports its phase-referenced cut stamp over the
  same CAN → same fusion.

## 8. Pro vs Max sketch delta (one table)

| | Pro | Max |
|---|---|---|
| Compute | ESP32-C6 + TJA1051 | ESP32-P4 + GW5A-25 (digitizer only) + TJA1051 |
| Load plane | R-banks + 8 verniers + ONE fast channel (12V-2x6 path) | + switch matrix (fast channel → EPS too), optional 2000 W banks |
| Analog add-ons | ripple *indicator* + scope BNC taps | 20 MHz AFE ×4 → mux → AD9253 (spec-grade ripple, waveforms) |
| OVP | not claimed | TPS55289 sourcing stage behind relay |
| Hold-up | T6-only (DC-side) | + phase-controlled AC interrupter accessory (absolute 12/17 ms) |
| Data out | CAN events + report via Hub | + USB-HS waveform pulls |
| Chassis/cooling | identical 1600 W console | identical (+1 fan w/ 2 kW option) |

## 9. Open sketch questions (for the schematic pass)

1. R-bank step ladder per channel (binary vs 1-2-5) + exact leg counts.
2. Vernier count: one per big channel (8, matches DAC80508) vs shared bank
   with a routing matrix (fewer FETs, more relays — lean per-channel).
3. Fast-channel switch matrix (Max) realization: contactor vs paralleled
   fixture-block slices (lean: second slice, no matrix inductance).
4. Front-plate mechanical standard for the OQ-89 heads (this drives the
   consumable SKU geometry — coordinate with OQ-89 before either freezes).
5. MARK frame ID + mark-table firmware home (extend cec_freeze vs new
   cec_mark component) — OQ-85 contract chapter.
6. The 5VSB 3.5 A/500 ms peak test wants one small dedicated linear stage —
   fold into the 24-pin group vernier or standalone? (~$3 either way.)
