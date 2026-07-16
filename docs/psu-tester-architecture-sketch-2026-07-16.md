# PSU tester — architecture sketches (componentry, speed, cooling, form, data, timing)

SKETCH (2026-07-16, owner-requested). **REV B (owner, same day — supersedes
REV A's hub-role reading):** the tester is **just another module,
technically** — it plugs into the Hub like any module, as part of a BENCH
SUITE (Hub + measurement modules + tester). It is never deployed inside a PC,
but it does NOT take over the Hub's job. Its tier links are its OWN
module-side uplinks: the **Pro tester streams RS-485** (pins 4/5, the Pro
module pattern) and the **Max tester carries bidirectional 100BASE-T1**
(pair 2, the Max module pattern) — carrying the tester's high-rate actuation
data (fast-channel pulse-actual waveforms) up, and (Max, bidirectional)
profiles/commands down. It ALSO works **standalone over its own USB-C direct
to a PC — monitoring + SELF-POWER (USB-C PD)** — the §6.14 posture; standalone
= tester-only truth (coarse self-sense + trips), full measurement truth =
the suite. The REV A "tester absorbs the Hub" consolidation (a possible
"Bench Unit" SKU) is NOT ruled out — owner: *"needs in-field testing"* — and
is preserved as a deferred variant in §9. MCU verdicts SURVIVE for a
different reason: a Pro-tier streaming module is P4-class by platform
precedent (the 12VHPWR Pro is P4); Max = P4 + GW5A + ONE T1 PHY (not a
switch — that was hub-role hardware). Builds on: canonical
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
                 BENCH SUITE (REV B: the Hub stays; tester = one more module)
  PSU-under-test ──24-pin──▶ [24-pin module]──ext──▶┐
        │        ──EPS×2──▶ [EPS module]────ext──▶│  TESTER FRONT BAY
        │        ──PCIe×2/3▶ [PCIe module]──ext──▶│  (fixture heads on a
        │        ──12V-2x6─▶ [12VHPWR mod]──ext──▶│   replaceable plate)
        │                        ▲ modules + HUB dock on the MODULE DECK
        │
  HUB ◀─RJ-45─▶ modules  ◀─and─▶ TESTER's own module jack
   │              (CAN all; RS-485 streams → Hub Pro; T1 ↔ Max Hub)
   └── USB ──▶ Host PC          TESTER DETECT code: Pro = 4.7 kΩ (CAN+RS-485),
                                Max = 10 kΩ (CAN+100BASE-T1) — §2.3 as locked
  STANDALONE mode: Host PC ◀── tester USB-C (monitoring + PD self-power), no Hub
```

**Power domains (REV B):**
- **Tester self-powers via its USB-C PD sink** (~20 V/45–60 W request): brains
  + DACs + gate rails + fans. In-suite (Hub present, PC on the Hub's USB) the
  tester's USB-C simply plugs a wall USB-C charger; standalone it plugs the
  PC and carries data too. On a 5 V/15 W-only source, firmware derates the
  permitted test power to the available fan budget and says so on the report.
  Optional 12 V aux barrel. The load plane itself needs no supply.
- **The instrumentation survives DUT death platform-natively**: on the bench
  suite the Hub runs from its §2.9 wall-wart leg (the third source exists for
  exactly this posture) and feeds module VCC — so hold-up/SCP/shutdown tests
  never brown out the instruments. The DUT's 5VSB is only ever a measured
  rail; **the DUT never powers tester or instrumentation.**
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

## 3a. Protection-test coverage (OCP / OPP / OVP / SCP / UVP)

| Test | Pro | Max | How |
|---|---|---|---|
| **OCP** (per rail) | **YES** | YES | Vernier/bank staircase ramp until trip; trip edge stamped µs-grade by the §6.13 comparators (the 1 kHz INA path is the wrong clock — canonical OQ-11); records trip point + latch-vs-retry recovery via the PS_ON#/PWR_OK sequencer. Pass framing = Cybenetics convention (≤130 % single / ≤135 % multi; Intel publishes no numeric). |
| **OPP** (whole-PSU) | **YES, bounded by installed sink** | YES (+2 kW option) | Coordinated multi-channel ramp. 1600 W installed hunts OPP on PSUs up to ~1.2 kW rated (OPP typically 120–150 % of label); the Max 2 kW ballast option extends to ~1.5 kW-class flagships. Plus the ATX 3.1 discrimination test the excursion channel makes possible: a compliant unit must RIDE 200 %/100 µs pulses without tripping yet still trip on sustained overload — both sides on one timeline. |
| **OVP** | **YES — check-grade (RULED §3d)**: go/no-go + module-measured trip voltage | **YES** (characterization: ramps, dV/dt, statistics) | A sink can only pull a rail down; OVP needs voltage SOURCED into the rail. Max carries the TPS55289 current-limited I²C sourcing stage behind a relay, walking the rail into the Table 4-13 windows (12 V 13.4/15.0/15.6, 5 V 5.74/6.3/7.0, 3.3 V 3.76/4.2/4.3) until the PSU latches. Pro's report prints "OVP: not tested (requires Max)". |
| **SCP** | YES | YES | Crowbar FET short (<0.1 Ω), spec-sanctioned-scary (canonical §3e): fire-posture workflow, PSU must survive by spec; 5VSB indefinite-short leg included. |
| **UVP** | (via T6) | (via T6) | Intel defines no output-UVP number; the spec mechanism is PWR_OK deassert — covered by the T6 early-warning test (>1 ms before rails leave regulation), measured by the 24-pin module. |
| OTP | NO | NO | Requires heat-soaking the DUT — out of scope both tiers (standing fence). |

## 3b. SCP mechanics — how the scary test is made safe

The short is applied by a **dedicated crowbar block per testable rail** —
never through the load channels — at the fixture head, through the DUT's own
cable (the realistic short location the spec intends):

```
rail @ fixture ─▶ crowbar: [fuse] ─ [commodity switch-FETs ∥, mΩ, fully enhanced] ─ [~30–50 mΩ
                 surge shunt (doubles as the sensor)] ─▶ RETURN;  TVS across the FET stack
```

- **Energy reality:** the initial cap dump is trivial (½CV² of a beefy 12 V
  rail ≈ 0.3 J). The sustained phase is the DUT's own OCP-limited current
  (~100–150 A on a big single-rail unit) for the few ms until ITS protection
  trips — the crowbar FETs are fully-enhanced switches (2–3 mΩ commodity
  parts, ∥), so they dissipate tens of watts for milliseconds: pulse-SOA
  trivial. This is switching duty — the linear-L2 rules don't apply here.
- **The <0.1 Ω spec budget** is met by FETs + shunt + harness; the deliberate
  30–50 mΩ shunt both bounds peak current and records the surge waveform
  (Max: routable into an AFE channel).
- **Backstop ladder for a DUT that refuses to trip** (the fire case):
  (i) firmware timeout releases the crowbar after ~50–100 ms of no-collapse —
  release at controlled di/dt (gate resistor) with the TVS absorbing the
  harness ½LI² kick (~2 µH at 150 A ≈ 23 mJ — TVS territory);
  (ii) a series fuse in the crowbar path sized on TIME (carries the ms-scale
  test surge, blows on seconds-scale cook) — works with firmware dead;
  (iii) the existing de-gate rail + bimetal plate switches.
- **Protocol posture:** SCP runs LAST in a sequence (data already banked if
  the DUT dies), two-step software arm, stand-clear workflow + fire-resistant
  bay assumption (canonical §3e). Hiccup-mode DUTs: the crowbar holds through
  N retry cycles to characterize them, then releases; latch-mode: release →
  re-sequence PS_ON# → verify recovery. The 5VSB indefinite-short leg gets
  its own small continuously-rated crowbar (5VSB OCP is ~4–5 A — trivial).

## 3c. Hold-up + AC-cut timing WITHOUT a mains product — the AC SENSE POD

**PROPOSED (2026-07-16, answers the owner's cert question; supersedes the
canonical §6 Max item 4 "AC-interrupter accessory" if ratified — owner nod
needed since that item was part of the tier ruling).** The insight: the
hold-up test needs (a) something to CUT the AC and (b) precise knowledge of
WHEN it cut. Only (b) needs precision — and (b) can be sensed **without ever
being in the AC path**:

- **The cut**: any commodity LISTED switching device the shop already has or
  buys — wall switch, or an off-the-shelf enclosed relay/SSR box with a SELV
  trigger input (IoT-relay class) that the tester drives from an isolated
  3.5 mm TRIGGER OUT jack. Bonus physics: a zero-cross SSR box *releases at
  the next current zero* — the cut phase is inherently quantized and
  repeatable, no phase-controlled CEC hardware required.
- **The truth**: the **CEC AC sense pod** — a cord-clip accessory that is
  never galvanically in the circuit: a capacitive E-field pickup (non-contact
  voltage-tester physics) + a split-core clamp CT (isolated by construction),
  a comparator edge detector, and a cable to the tester. It watches the live
  waveform (phase + zero-cross train) and stamps the cut edge; the tester
  puts that edge on the CAN MARK timeline like every other event.
- **Resolution**: edge detection is sub-ms conservative (~100 µs typical
  mid-phase; near-zero cuts are disambiguated by the CT current envelope +
  repeat runs) against a 12,000 µs pass limit — and on the **Max tester the
  pod's analog output feeds one AFE mux input**, so the AC collapse is
  captured SAMPLE-EXACT in the same digitizer window as the rail waveforms.
  That is "AC-cutoff data at Max resolution" with zero mains-path product.
- **What this upgrades**: absolute hold-up (Table 4-8: 12 ms @100 % /
  17 ms @80 %) and true T5 become **both-tier tests** (Pro gets µs-stamped
  edges; Max gets waveforms) — the "T6-only on Pro" fence falls. Protocol:
  pod watches phase → tester (or operator) triggers the cut → pod stamps t0
  → 24-pin module stamps PWR_OK deassert (T5) → module rings stamp
  rails-out-of-regulation (hold-up) → repeat across phases for statistics.
- **Cert honesty**: the pod is a SELV sensor accessory with the platform's
  ordinary unintentional-radiator/product-safety posture — the same bucket
  as every module. It is not a mains-rated instrument and never claims to
  be; the switching device is someone else's listed product. The
  phase-controlled AC-interrupter (a genuine mains product with its own
  listing burden) exits the roadmap entirely if this is ratified.

## 3d. Minimal OVP on Pro — **RULED: Option A (owner, 2026-07-16)**

The Max-only OVP fence was tier differentiation, not a cost wall — the
sourcing stage is cheap. **Owner ruling: Option A ships on Pro.** (Option B
retained below for provenance only. The canonical §6 tier-table amendment —
"OVP retiring fence at Max" becomes "check-grade on Pro / characterization
on Max" — folds into the spec at the Task-13-class pass.)

- **Option A (RULED): same part, firmware-scoped.** Put the identical
  TPS55289 stage (+relay, ~$15–25) on Pro, but firmware-limit it to a
  **go/no-go OVP CHECK**: lift the rail toward the Table 4-13 window-max
  (time-boxed, current-limited, ceiling capped just past window-max so an
  OVP-absent DUT sees only a ms-scale, margin-bounded lift), verdict =
  trips/doesn't + the trip VOLTAGE — which the inline MODULES measure for
  free (they are the voltmeter; 1 kHz is ample for a ms-class latch event).
  Max keeps "OVP characterization": programmable approach ramps, per-window
  dV/dt, repeatability statistics. One inventory line, honest tier split,
  fits the platform's quality-first ruling ("better even if it costs a bit
  more").
- **Option B (cheaper, clunkier): fixed-point checker** — a fixed ~16 V
  current-limited boost + resistor + rail-select signal relays (~$8–15),
  same go/no-go verdict. Saves ~$10 over A, adds a second design to
  maintain. Only worth it if Pro BOM pressure gets real.

Either way the Pro report line upgrades from "OVP: not tested" to
"OVP: checked (trip at X.XX V)" — a real shop-value bump for ~$15.

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
- **LID = the module deck**: a rail/tray where the inline modules AND the
  Hub click in (M3 mounts), so the PSU→module→extension→bay harness dresses
  flat and everything stays visible (LEDs), cool (upstream of exhaust), and
  strain-relieved; short RJ-45 patches run module→Hub along the deck. The
  tester's own module jack sits at the deck's edge beside them.
- **REAR = all heat + power**: exhaust grille, the **USB-C (PD self-power;
  + data when standalone)**, optional 12 V aux barrel, the AC-sense-pod jack
  + isolated SELV TRIGGER-OUT jack (§3c, both tiers). NOTHING hot or cabled
  faces the operator.
- **DUT parking**: beside the tester (PSUs vary too much to swallow one);
  optional side tray accessory later. Front-bay cable reach sized for a PSU
  sitting flush left or right (~0.5 m harness envelope).

## 6. Data plane (in and out)

- **The tester is a module on the platform interface** (REV B): one RJ-45 to
  the Hub — DETECT 4.7 kΩ (Pro, CAN+RS-485) / 10 kΩ (Max, CAN+100BASE-T1),
  CAN for control + 5 Hz cec_telem (set-vs-actual per channel, plate temps,
  fan RPM, faults), poke-ack responder, CAN-OTA updatable like every module.
  Its tier link is its own UPLINK: **Pro streams RS-485 to Hub Pro** — the
  fast channel's pulse-actual shunt waveform (100–500 kS/s bursts during
  excursion trains) is what earns the stream; **Max runs bidirectional T1**
  (same data up; big profiles and bench-mode commands down at link rate).
  Profile upload rides CAN (Pro; step lists are small) or T1 (Max) or USB
  (standalone).
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
- **Host link, two postures** (REV B): IN-SUITE the host PC sits on the
  Hub's USB as always — the tester's data reaches it like any module's
  (CAN telemetry + its RS-485/T1 stream through the Hub). STANDALONE the
  tester's own USB-C (HS on the P4) carries monitoring + control + PD
  self-power — the §6.14 posture with the OQ-85 CDC/HID composite identity.
  Max digitizer windows: through the Max Hub's egress in-suite, or the
  tester USB standalone.

## 7. Cross-timing to the modules (the measurement-truth clock)

The platform already owns the mechanism: a high-priority CAN broadcast is
received by every node within ~1 bit time, and modules already ISR-timestamp
such frames (cec_freeze). The tester is just another node on the suite's CAN
(REV B) — it broadcasts MARKs, everyone stamps. Extend, don't invent:

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
| Compute | **ESP32-P4** + TJA1051 + RS-485 TX (REV B: the Pro-tier streaming-module pattern — same reason the 12VHPWR Pro is P4) | ESP32-P4 + GW5A-25 (digitizer only) + ONE 100BASE-T1 PHY (module link, §13.2a pattern) + TJA1051 |
| Load plane | R-banks + 8 verniers + ONE fast channel (12V-2x6 path) | + switch matrix (fast channel → EPS too), optional 2000 W banks |
| Analog add-ons | ripple *indicator* + scope BNC taps | 20 MHz AFE ×4 → mux → AD9253 (spec-grade ripple, waveforms) |
| OVP | not claimed | TPS55289 sourcing stage behind relay |
| Hold-up | **absolute (12/17 ms) via the AC sense pod + any commodity listed cut switch** — §3c | same, + pod analog into the AFE = sample-exact cut waveform |
| Data out | in-suite via Hub (CAN + RS-485 stream); standalone via own USB-HS | in-suite via Max Hub (CAN + T1 bidir); standalone via own USB-HS |
| Chassis/cooling | identical 1600 W console | identical (+1 fan w/ 2 kW option) |

## 8a. Honest BOM roll-up (REV B basis; sketch-grade ±, freeze at schematic)

| Line (class prices, canonical + component-research basis) | **Pro** | **Max adds** |
|---|---|---|
| Resistive banks (~3.2 kW installed @100 W alu-shell + plates) | $200–300 | — (+$100–150 for the 2 kW option) |
| Bank switching (commodity FETs, drivers, fuses) | $50–80 | — |
| Linear verniers (8× L2 + ballast + sink share; SKU-ladder swing TO-247 vs TO-264) | $150–350 | — |
| Fast excursion channel (3–4× L2, fast loop, shaper, Kelvin shunt) | $150–250 | 2nd channel/matrix +$150–250 |
| Loops + analog (8 op-amps, DAC80508, 8× INA181+TLV7011, ref) | $60–90 | — |
| SCP crowbar blocks (3–4 rails, §3b) | $40–70 | — |
| Control (ESP32-P4, TJA1051, RS-485 TX, PD sink, misc) | $30–45 | T1 PHY +$5–8; PSRAM/support +$5–10 |
| Digitizer lane (AD9253-80 + GW5A-25 + 4× 20 MHz AFE + mux) | — | +$115–130 |
| OVP source (TPS55289 + relay + protection) | $15–25 (RULED on Pro, §3d) | included (characterization firmware) |
| AC sense pod (bundled, §3c) | $15–30 | — (pod analog → AFE is free) |
| Fixture heads + front plate + internal bus | $80–120 | — |
| PCBs (4-layer 2 oz, large) | $40–80 | +$10–20 |
| Chassis, FET extrusion, fans, duct | $250–400 | — |
| **BOM subtotal** | **~$1,065–1,815** | **~$1,365–2,260** (+2 kW option) |
| Landed (+18–20 %, canonical convention) | ~$1,260–2,180 | ~$1,610–2,710 |
| vs. ruled list ($3,495–3,995 / $5,995–6,995) | 1.8–2.8× | 2.2–3.7× |

Deltas vs the canonical §6 table, honestly: the top of the Pro band rises
~$100–200 because SCP blocks, the pod, and PCBs are now explicit lines the
canonical folded into coarse classes; the Max band DROPS ~$100–150 because
the mains AC-interrupter accessory ($80–150 + its own cert program) is
replaced by the $15–30 sense pod. The canonical margin-honesty note stands:
the low-mid BOM holds the ~3× convention; the high end runs
capital-equipment multiples (1.8–2.5× is test-gear-normal) — owner call at
pricing lock.

## 10. Quality & reliability refinements (owner directive 2026-07-16: "extremely solid and reliable")

1. **POST before every sequence**: bank legs switch-verified (loop-shunt
   deltas), vernier loops nulled, comparators sanity-pulsed, fans spun-up on
   tach, NTC plausibility — a tester that self-verifies before it asserts
   verdicts. Plus per-sequence **auto-zero** (all-off shunt read → offset
   null) killing the op-amp/shunt offset drift term.
2. **The modules calibrate the tester (cross-cal)**: at sequence start the
   tester holds known DC plateaus while the inline modules (the accuracy
   story, ±0.5–1 %) read truth; firmware fits gain/offset for every tester
   loop chain INCLUDING the fast channel's shunt — so the Pro pulse-actual
   stream inherits module-grade DC accuracy, with pulse flatness carried by
   design (AN133 discipline). The traveling standard is built into every
   station; no cal lab, no annual sticker — every test is freshly cross-cal'd.
3. **Setpoint chain honesty (verified)**: DAC80508 internal ref 2.5 V at
   2 ppm/°C typ, TUE ±0.1 % FSR max, INL ±1 LSB — setpoints are honest to
   ~0.1–0.2 % class before cross-cal even runs
   <https://www.ti.com/product/DAC80508>.
4. **Derating doctrine at 40 °C design ambient** (shop-in-summer, not lab
   25 °C): linear FETs ≤50 % of derated SOA/power, resistors ≤50 % rating,
   105 °C-rated capacitors only, NO electrolytics on the load plane,
   AEC-Q-grade jellybeans where the cost delta is ~zero (quality-first
   ruling applies).
5. **Fans are the wear item — treat them like it**: dual-ball-bearing 120 mm
   PWM with tach, field-replaceable on standard pinouts without unsoldering,
   fan-fail → derate-not-die, filter-free duct (shop dust) with a cleanable
   rear grille.
6. **Front-plate odometer**: the fixture heads are ~30-mating-cycle parts;
   each plate carries an ID strap and the tester counts matings in NVS per
   plate ID → "replace plate" prompt on the report. Consumable managed, not
   discovered.
7. **Loop robustness vs the real world**: compensation validated against a
   worst-case DUT-cable matrix (long/braided/high-inductance) as a bench
   gate; a firmware oscillation detector (comparator-chatter heuristic) →
   auto de-gate + flagged report line, never a cooked FET.
8. **Interlock state machine**: IDLE→POST→ARMED→RUN→SAFE; SCP and OVP
   require two-step arm; profiles carry CRC; PD renegotiation or brownout
   mid-test → SAFE + derate + annotated report. Watchdog de-gate + bimetal
   backstop per §3b/§4.
9. **Every external port protected**: USBLC6 on USB, PESD on CAN/DETECT
   (platform patterns), TVS on the trigger/pod jacks, reverse-polarity-
   tolerant aux barrel.
10. **Provenance on every verdict**: per-unit cal record + firmware version +
    profile CRC + cross-cal residuals printed on the report footer — the
    platform's verdict-provenance doctrine applied to a shop deliverable.

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
7. **AC sense pod ratification** (§3c): owner nod to supersede the canonical
   §6 Max item-4 AC-interrupter accessory; then bench items — pod edge-detect
   latency vs cut phase (esp. near-zero cuts), pickup geometry on typical IEC
   cords, CT clamp part class, and whether a resold IoT-relay-class listed
   box joins the kit list or stays shop-supplied.
8. **SCP crowbar sizing pass** (§3b): FET ∥-count + fuse time-current pick vs
   the biggest single-rail DUT class (150 A OCP assumption to verify), TVS
   energy rating, release-di/dt value.
9. **Station topology (OWNER: "needs in-field testing" — deliberately
   unresolved):** DEFAULT = this REV B suite (Hub + modules + tester-as-
   module). DEFERRED VARIANT = the REV A "Bench Unit" consolidation (tester
   absorbs the Hub role: port VCC/DETECT/CAN termination + RS-485/T1
   ingest — the hardware sketch for it lives in this doc's git history at
   the REV A commit). Owner's lean: consolidation "feels clumsy"; decide
   from field feedback, not architecture taste.
