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
| **OPP** (whole-PSU) | **YES, bounded by installed sink** | YES | Coordinated multi-channel ramp. 1600 W installed hunts OPP on PSUs up to ~1.2 kW rated (OPP typically 120–150 % of label); the **Workstation tier (§13, ~3 kW installed) extends the hunt to ~2.4 kW-class labels** — the old Max 2 kW ballast option is RETIRED (owner 2026-07-16, §13). Plus the ATX 3.1 discrimination test the excursion channel makes possible: a compliant unit must RIDE 200 %/100 µs pulses without tripping yet still trip on sustained overload — both sides on one timeline. |
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

### §3b addendum — modules in the SCP path: ratings verdict (owner Q, 2026-07-16 night)

The docked CEC module is INLINE in every SCP event (actuator-not-instrument:
the module IS the per-connector recorder). Verdict: **no continuous-rating
or spec change on any module** — the crowbar's deliberate 30–50 mΩ surge
shunt Ohm's-law-bounds BOTH phases of the event (peak ≈ 300 A/~50 µs cap
dump; sustained ≈ 150–200 A ms-class regardless of a 3 kW DUT's OCP,
because 12 V / (40 mΩ crowbar + 20–30 mΩ cable/module loop) caps it), and
every module path element passes adiabatic I²t with factors of margin.
Worst-case ledger at the 100 ms firmware-backstop release (the longest the
event can exist):

| Element (worst family) | Continuous basis | SCP exposure (peak / ms / 100 ms backstop) | Verdict |
|---|---|---|---|
| EPS/PCIe 0.5 mΩ CSS2H shunt | 6 W class | 45 W·50 µs / 11–20 W / 1–2 J | pass, factors |
| 24-pin 12 V 2 mΩ shunt | 6 W class | 180 W·50 µs / 45–80 W / ~4.5 J → tens-of-K element rise | pass — the warmest element; bench-verify |
| 24-pin 12 V Mini-Fit pins (×2) | 9–13 A/pin | 150 A·50 µs / 75–100 A / ~3–5 J/contact ≈ 10–15 K | pass — second warmest; bench-verify |
| EPS pins (×4) / blades (3/polarity) | 9–13 A / 22.9 A | 75 A / 38–50 A per pin ms-class | pass |
| 12V-2x6 pins (×6) + 1 mΩ/pin shunts | 9.2 A/pin | 50 A / 25–33 A per pin ms-class | pass |
| Module pours (≥1 mm² min-cut class) | ~52 A/cable design | 150–200 A/mm² @100 ms ≈ 2–4 % of Onderdonk fusing energy | pass |
| INA front-ends (181/238/240) | CM abs-max 26/85/80 V | CM collapses 12→~0 V (in range); diff stays mV; release kick clamped fixture-side (TVS) + PSU caps module-side | pass; measure release envelope at proto |

Notes that ride into contracts/checkers (DESIGN-SHEET rule 24): module
channels SATURATE during the surge (INA outputs clip at rail) — the crowbar
surge shunt is the calibrated surge recorder, module data = event mark +
µs timestamps + the collapse trace; 5VSB SCP = a supply-swap event for the
instrumentation stack (deck 5V_SYS swaps to the tester-PD source via the
§2.9 three-source posture — the mux/hold-up ride-through the owner already
ruled covered); bench adds an SCP-surge leg to the OQ-88 soak (N surges →
contact-R + shunt-R drift); firmware may tighten the per-head backstop
timing if bench asks.

**ARM RELAY addendum (owner Q 2026-07-17: "use a relay to fully disarm the
crowbar?" — YES, adopted):** each SCP block gains a series relay upstream
of its branch, giving a GALVANIC third disarm layer on the most destructive
actuator in the box. Duty is deliberately benign — the relay is
**dry-switched only** (closes before arm, opens after the event, with the
FET off and zero current; the FET does all fast/hot switching, the
time-fuse keeps the stuck-FET backstop), so contact life is mechanical and
the only electrical duty is SURGE CARRY: ~230 A × ms-class ≈ 100–500 A²s
through pre-closed contacts → 70–100 A automotive-class relay ($3–8),
paralleled contacts acceptable. What the galvanic break buys beyond the
existing two layers (de-gate rail + arm bits): (a) a spurious fire is
impossible with the branch absent — gate transients, dV/dt Miller lift on
DUT hot-plug edges, firmware bugs all have nothing to actuate; (b) a
FAILED-SHORT FET (the way FETs die) is DETECTABLE before it matters — the
**crowbar pre-flight self-test**: relay open, bias the drain node, verify
no conduction; relay closed (still disarmed), verify continuity through
fuse+shunt — a shorted crowbar is caught at power-on self-test instead of
discovered as an instant fuse event on the customer's next DUT connect;
(c) the disarmed branch's SMCJ15A no longer loads the rail if any test ever
drives it above TVS standoff. CONTROL COSTS ZERO NEW BITS (pools are full):
the existing per-block 595 ARM bit drives the relay coil (via a small
coil transistor) instead of a logic gate — the layering becomes (1) 595
arm bit = relay closes, (2) de-gate rail (direct GPIO) = gate drivers
alive, (3) comparator/direct-GPIO = fire; three independent layers, two of
them physical. Front-panel visibility: ARMED state surfaces on the main
LCD + bay screens (a keyed physical ARM switch stays an SE-tier idea).
BOM: +4 relays + coil drivers ≈ +$15–35/unit (§3d line pending sourcing
pass). Rule 24 checker addition: relay coil node reachable ONLY from the
arm bit (never the fire path), and the branch-absent self-test is a
REQUIRED power-on sequence in the firmware contract.

**MAINS-SIDE IMPACT of the SCP event (owner Q 2026-07-17; manual/FAQ
material — "will this trip my shop's breakers?"):** No — the event never
meaningfully reaches the wall. Designed event ≈ 230 A × 12 V × 1–2 ms ≈
5 J at the DUT output vs 30–40+ J already stored in the DUT's primary
bulk cap: the short runs on stored energy, and the PFC front-end's
deliberately slow loop (~10–20 Hz) cannot ramp mains draw within a ms
event; then the DUT's SCP (the thing under test) cuts draw to ~zero. A
15/20 A thermal-magnetic breaker needs 5–10× rating (75–200 A) for a
half-cycle (magnetic) or sustained overload for tens of seconds
(thermal) — the wall never sees more than normal draw for a few cycles;
the DUT's own plug-in inrush (40–100 A half-cycle) is harsher than our
test. GFCI: no earth-path current (isolated secondary event); AFCI:
double-filtered (transformer + DUT EMI front-end). Edge cases: SCP-fail
hiccup = few-hundred-W blips (nothing); catastrophic DUT primary failure
= the DUT's internal fuse blows first (wall breaker is third in line
behind our time-fuse and the DUT fuse). The REAL panel constraint is
steady-state: W-tier 3 kW output ≈ 27 A at 120 V = thermal trip in
minutes on a 15 A circuit — the §13 ruling (240 V / dedicated-circuit
bench guidance for W), unrelated to SCP transients.

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
  delivered → **4× Arctic S12038-4K** (OWNER STEER 2026-07-16; spec-sheet
  checked: 120×120×**38** mm server fan — 11.45 mmH₂O static / 106 CFM
  free-air / 600–4000 rpm PWM / dual Japanese ball bearing in brass / 3.96 W
  / motor-cooling hub impeller / 6-yr warranty / $14.99 — MORE pressure than
  the round-2 Noctua iPPC-3000 pick at half the price; budget the duct mouth
  for the 38 mm depth), ducted (open-frame CFM ratings don't survive a
  resistor tunnel; budget ~2× nameplate). Workstation tier (§13): ~3,000 W @
  ΔT 20 °C → ~263 CFM delivered → **6× S12038-4K**, two-lane duct (the extra
  fans also let the PWM curve sit lower for the same flow). The old "2000 W
  Max option = +1 fan" line is RETIRED with the ballast (owner 2026-07-16,
  §13). Acoustics posture unchanged: PWM floor 600 rpm keeps small tests
  civil; full-power is loud and documented as such.
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
- **DISPLAYS (owner add, 2026-07-16): the box shows its load on its face.**
  One MAIN front-panel TFT (2.8″ IPS 320×240 SPI class, ~$5) above the
  connector bay: total W, per-rail summary, sequence state
  (IDLE/POST/ARMED/RUN/SAFE), fault code. Plus **one small screen per module
  bay** on the deck (1.54″ IPS 240×240 SPI module class, ~$3/bay —
  BOM-checked and RULED IN at that cost): each bay renders ITS module's live
  readout (V/A/W for that connector family); an **unpopulated bay sits dark
  or shows the CEC logo splash**. IPS TFT deliberately, NOT OLED — static
  numeric readouts burn OLEDs over shop-years (§10 reliability posture).
  Drive: one shared SPI bus + 74HC595 CS fan-out + shared backlight PWM
  (trivial on the P4; fits the ST tier's C6 pin budget via the same
  expander); 5–10 Hz numeric repaint. The bay screens are **cec_telem
  renderers** (§6) — the tester already hears every module's telemetry on
  the suite CAN, so this is firmware + glass, zero new protocol. Standalone
  (no modules docked) they show the tester's own loop-shunt actuals tagged
  "actuator-grade" — the accuracy doctrine stays honest on-glass.

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
- **Bay screens are pure telemetry renderers** (§5 displays): the per-bay
  LCDs repaint the 5 Hz cec_telem frames the tester already receives as a
  bus node — no new data path, no waveforms on glass, and the main screen's
  total-load figure is the same joined view the host report uses.

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
| Load plane | R-banks + 8 verniers + ONE fast channel (12V-2x6 path) | + switch matrix (fast channel → EPS too); 2000 W bank option RETIRED (owner 2026-07-16 → Workstation tier, §13) |
| Analog add-ons | ripple *indicator* + scope BNC taps | 20 MHz AFE ×4 → mux → AD9253 (spec-grade ripple, waveforms) |
| OVP | not claimed | TPS55289 sourcing stage behind relay |
| Hold-up | **absolute (12/17 ms) via the AC sense pod + any commodity listed cut switch** — §3c | same, + pod analog into the AFE = sample-exact cut waveform |
| Data out | in-suite via Hub (CAN + RS-485 stream); standalone via own USB-HS | in-suite via Max Hub (CAN + T1 bidir); standalone via own USB-HS |
| Chassis/cooling | identical 1600 W console | identical (+1 fan w/ 2 kW option) |

## 8a. Honest BOM roll-up (REV B basis; sketch-grade ±, freeze at schematic)

| Line (class prices, canonical + component-research basis) | **Pro** | **Max adds** |
|---|---|---|
| Resistive banks (~3.2 kW installed @100 W alu-shell + plates) | $200–300 | — (2 kW option RETIRED → §13 Workstation) |
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

## 8b. Load-plane architecture survey — "any fancier way?" (owner Q, 2026-07-17)

_Owner asked whether staircase+vernier+fast-channel is the best shape for
Pro/Max or whether fancier/more-accurate/outside-the-box architectures win.
Steelmanned survey; verdict = the hybrid stands, four refinements adopted._

**Alternatives examined and where they lose:**
- **All-linear FET plane** (Chroma/Itech/Kikusui shape — every watt in FET
  SOA on heatsinks): infinitely programmable, native CV/CR/CP — and it is
  exactly why commercial 3 kW loads cost $10–30k: 20–30 linear devices AT
  their thermal budget, Spirito hot-spotting as the fleet failure mode, same
  total heat as resistors but in $13–28 silicon instead of $2–3 ceramic at
  48 % derate. Our hybrid puts ~85–90 % of the power in bulletproof
  resistors and spends SOA silicon ONLY on interpolation + dynamics — that
  asymmetry IS the price wedge. REJECTED as baseline (it is the competitor's
  shape, not an upgrade).
- **Regenerative / switched-mode load** (energy-recycling PFC front end,
  Chroma 63800R / EA-ELR class): genuinely outside-the-box, ~90 % of 3 kW
  pumped back instead of heated — and wrong for a FIDELITY instrument: a
  switching converter input injects its own ripple/EMI into the DUT's output
  (corrupting exactly the ripple/transient truth the ecosystem measures),
  the input filters that tame it soften transient edges, and grid-tie adds
  a UL-1741-class cert program. PARKED as a possible future **burn-in-farm
  SKU** (24/7 duty shops, power-bill economics — different product, real
  market; owner-queue note).
- **PWM-chopped resistor banks** (synthesize intermediate values by chopping
  a leg at kHz): resolution without linear FETs — REJECTED ON PRINCIPLE:
  it injects switching noise into the DUT at exactly the frequencies we
  grade; the vernier does the same job silently. Recorded so the tempting
  cost-down never sneaks back in.
- **CR-vs-CC honesty note**: banks are constant-resistance (draw sags with
  a drooping rail — ~0.5 % at ATX droop limits, negligible for baselines);
  everything spec-shaped that must drive INTO a droop or collapse (OCP
  ramps, excursions, SCP) already rides the CC loops (verniers/fast
  channel). Right tool per role; no change.

**Adopted refinements (the question's real yield):**
1. **DAC80508 setpoints at Pro/Max baseline** — pull the W-tier's 16-bit
   DAC (§13) down: PWM-RC setpoints ripple through the CC loops as
   load-current ripple at the PWM frequency; ST keeps PWM-RC (its class),
   Pro/Max get real DACs (~$7/board, 8 ch/chip). [OWNER NOD — queued.]
2. **Closed-outer-loop + calibration conductance map = precision from ±5 %
   parts (FIRMWARE CONTRACT, record now):** the staircase's ±5 % RX24
   tolerance never reaches the user because (a) firmware closes the outer
   loop on the MEASURED total (platform-grade shunts) and trims the vernier
   setpoint, and (b) at calibration each group's real conductance is
   measured and stored, so staircase planning uses actual values. The
   resistors provide POWER, the measurement chain provides TRUTH — accuracy
   lives in the shunt/ADC chain we already build. Goes into the firmware
   contracts doc with the tester runtime (SB-07 family).
3. **FPGA-timed bank switching on Max**: route group-enable strobes through
   the GW5A so staircase steps land with sub-µs determinism on the CEC_MARK
   timeline — bank recruit/release becomes a characterized stimulus edge
   (Pro's MCU-timed ±tens-of-µs stays fine for its class). Costs a routing
   decision at Max capture, not parts.
4. **SCP arm relay** (owner's same-night question): adopted — see §3b
   addendum + DESIGN-SHEET rule 24; galvanic third layer, zero new control
   bits (the existing 595 arm bit drives the coil), enables the crowbar
   pre-flight self-test.

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

## 11. Standard tester — UN-SHELVED as the value line (owner, 2026-07-16)

**Owner ruling evolution**: the §6 canonical ruling shelved the Standard
tester ("Standard is not the shop spec"); owner direction 2026-07-16 un-
shelves it as a defined VALUE LINE for newer/smaller repair shops — "a
$1,000–1,500 tester that is already ATX-loaded and ready to go," doing the
"is this PSU sane under load, and does it work" job handheld testers only
pretend to. Two power classes: **ST-1000 (~1000 W)** and **ST-1300
(~1300 W)**.

**Feature fence (the §3a insight — switched-R is ADEQUATE for exactly this
set):** static per-rail loads + regulation verdict, PS_ON#/PWR_OK timing
(T1/T3/T6), power-up cross-load corner, OCP-by-steps (coarse staircase),
SCP, 5VSB incl. the 3.5 A peak leg, −12 V presence, 12VHPWR per-pin
melt-watch soak, one-button report. NO transient engine, NO OVP, NO
streams/digitizer, ripple = one BNC tap. The $15-tester kill-line:
*"it tells you it turns on; this tells you it works."*

**Architecture deltas from Pro (strip list):**
- **MCU returns to ESP32-C6** — the tier symmetry completes: C6/CAN-only
  (Standard), P4/RS-485 (Pro), P4+FPGA/T1 (Max). No streams → FS USB is
  ample; setpoints via PWM+RC (loop-grade), no DAC80508.
- Load plane: switched R-banks (~2:1 installed:tested at 50 % derate) + ONE
  small 2-device L2 vernier for corner smoothness and OCP ramps; no fast
  channel; SCP crowbars kept (cheap, high shop value).
- **~~PROPOSED carve-out — INTEGRATED instrumentation~~ RETIRED (owner ruling
  2026-07-16 evening: "soldered is worse in both repairability and cost
  savings makes no sense" — the §12 slot-bundle IS the ST architecture;
  text retained for provenance):** the
  module sensing BLOCKS (INA238 per rail-group, INA240 ×6 per-pin on the
  12VHPWR input, the 24-pin's 74LVC1G17 PS_ON/PWR_OK buffers) live ON the
  tester board at the fixture inputs, factory-calibrated, ±1 %-class. One
  box, one USB, nothing else to buy — literal "ready to go." The RJ-45 +
  2.2 kΩ DETECT stays, so the ST tester still joins a Hub suite later as
  the load node (upgrade path intact); its integrated sensing then defers
  to inline modules when present.
- Cooling: same doctrine, smaller — 1000 W ≈ 88 CFM (2 fans), 1300 W ≈
  115 CFM (3 fans); same console family, shorter duct. Fan SKU: unify on the
  Arctic S12038-4K (owner fan steer 2026-07-16; +$4–6 over the P12 Max buys
  one spare-fan SKU platform-wide + kills any ST duct-pressure doubt).
- **Displays KEPT at ST** (owner add 2026-07-16, §5): main screen + ~6 bay
  screens ≈ $28 — the value line's "ready to go" face; a $1,299 box that
  shows live per-connector numbers on glass is the whole demo.

**Block diagram:** `docs/assets/st-tester-block-2026-07-16.svg` (black-box
overview: deck/instruments vs load-plane/actuator split, control, UI,
thermal, SKU deltas, PROPOSED items marked).

**BOM sketch (integrated config):** ST-1000 ≈ **$537** (sensing blocks ~$35,
vernier pack $37, R-banks+switching $135, SCP $26, chassis/fans/sink $152,
plate $85, PCBs $45, control $10, misc $27); ST-1300 ≈ **$585** (+R, +fan,
+chassis). Landed ≈ $639 / $696.

**Retail:** **ST-1000 at $1,299** (2.03× landed) and **ST-1300 at $1,499**
(2.15×) — single SKUs, instrumentation INCLUDED, inside the owner's window.
Margin honesty: ~2× is capital-equipment-normal but below the platform 3×
convention — same owner call as the Pro/Max high end, flagged not decided.
Position: above the $750–950 Kunkin-stack-plus-crimping floor, at dead
SunMoon money with 2026 capability, $2,200 clear of Tester Pro (whose
transient engine + streams + OVP + module composability carry the upsell).

## 12. Slot-in module bundles — the blade interface IS the tester interface
(owner idea, 2026-07-16 — PROPOSED, recommended for adoption)

**The idea:** the modules' output side is already the v1.4.0/iteration-7
blade architecture — module main board carries TE 63969-1 top-entry
receptacles; the sellable output daughterboard carries TE 63951-1 downward
blades and drops in. **Make the tester's module attachment the SAME
interface**: the tester deck presents per-family fields of upward 63951-1
blade posts, and a module is lowered onto them exactly as a daughterboard
mates — roles swapped, geometry identical. Electrically, **the tester is a
giant active daughterboard.** Then sell TESTER BUNDLES: that tier's modules
factory-slotted, Hub docked, cables routed.

**Why it's strong — everything hard is already ratified or proven:**
- **Current interface pre-qualified**: 22.9 A @30 °C-rise per joint (TE
  108-1706), the §2.8 ≥125 % margin policy, ratified joint counts (24-pin
  10 / EPS 6/cable / PCIe 6/cable) — zero new connector qualification.
- **Keying already checker-proven**: `check_output_daughterboards.py`
  asserts no rigid transform seats one family's tab set as a subset of
  another's — a PCIe module physically cannot land in an EPS slot. Extend
  the same checker to the tester's field drawing (including any per-family
  rotations the deck layout needs).
- **The 24-pin's J_SIG 1×4 blind-mates alongside the blades** (iteration-5
  design intent) — so PS_ON#, PWR_OK, and −12 V arrive through the slot
  itself: the tester's sequencing signals need no extra cable.
- **The fixture-plate consumable largely dies**: the module IS the fixture
  head. BOM: front plate $85–100 → blade field ~$5 (40× 63951-1 at
  $0.10–0.16) + J_SIG socket + support rails ≈ $35–45 all-in. Per-test wear
  moves to the module INPUT headers (ATX-standard parts, same as in-PC
  life) — mitigations: cheap commodity input-saver pigtails as the
  consumable, and modules themselves are field-replaceable units.
- **OQ-89 gets a second life as the "field kit"**: bundle modules ship
  without their retail daughterboard; the daughterboard+extension assembly
  sells as the un-dock kit — pull a module off the tester, daughterboard
  it, drop it inline in a customer's PC for in-situ diagnosis. The killer
  demo is a SKU.
- **Hub: dock bay, not absorption.** A deck bay holds the real Hub
  (Standard/Pro per tier) with molded channels routing short RJ-45 patches
  to each slot position — integrated *UX*, modular *architecture*. This is
  the sweet spot the §9 "Bench Unit" question was circling: the suite looks
  like one appliance without the tester taking the Hub's job. (Full
  absorption stays the deferred field-test variant.)
- **12VHPWR exception (by design, not oversight)**: its output is the
  captive soldered pigtail (v1.4.0 explicitly unchanged) — that position is
  a module TRAY + a male 12V-2x6 fixture head (with sideband straps) the
  pigtail plugs into. Same for 12VHPWR Pro.

**Effect on the ST integrated-sensing carve-out (§11): ADOPTED — owner
ruling 2026-07-16 evening ("slot bundle; soldered is worse in repairability
and cost"); the carve-out is RETIRED.** ST tester BOM drops ~$80 (plate out,
blade field in, integrated sensing deleted) ≈ $457; add the real Standard
module set + Hub Standard (~$95–105 landed, pricing-study figures) → bundle
landed ≈ $645 — within dollars of the integrated version — so **ST-1000
BUNDLE at $1,299 ships REAL modules + a REAL Hub at the same price**, the
actuator-not-instrument principle survives untouched at every tier, and
there is ONE tester architecture instead of two.

**The #1 mechanical flag (inherited, multiplied):** gang insertion force.
Iteration 7 already carries ≤26/44 N-spec per joint as an OQ-86 sample
item; a 24-pin module is 10 joints ≈ 260–440 N of press force — not a
thumb job. Options: bundles ship FACTORY-SLOTTED (arbor press; field swaps
use a simple press tool), or a deck cam/lever assist (real mechanical
design, DIMM-latch spirit). Extend the OQ-86 fit-check sample gate to
cover: measured gang insertion on real boards, blade-field position
tolerance across 10 joints, and module support rails vs the horizontal
mating shear of PSU-cable insertion.

## 12a. ST tester on the Hub's KVM aux header — PROPOSED (owner idea, 2026-07-16 evening; needs bounce/ratification)

**The idea (owner):** commandeer the Hub Standard's NanoKVM aux header
(J_KVM: 3.3 V UART + 5VSB + GND + ref/presence, §2.9 form, ESD'd + series-
protected, ALREADY placed/routed on every Hub Standard) as the ST tester's
link — freeing all FOUR RJ-45 ports for modules.

**Why it works at ST specifically:** the ST fence needs no µs-grade stamps
from the TESTER — T1/T3/T6 are measured by the 24-pin module (stays on CAN,
±2–10 µs), OCP staircases/cross-load are ms-class, melt-watch is thermal.
Architecture: tester→UART→**Hub relays CEC_MARK onto CAN** (Hub TX stamp =
timeline reference); tester clock maps via UART ping-pong calibration.
Honest budget at 921600 baud: ~±100–150 µs tester-stamp alignment — ~50×
worse than CAN membership, ~10× better than anything the ST fence measures.
Identity rides the UART protocol (no DETECT resistor on this path); tester
stays PD-self-powered.

**What it buys — DOWNGRADED to optional headroom (owner correction,
2026-07-16 late): "you don't need *both* PCIe and 12VHPWR at the same time
typically — we have enough slots on the Standard, just no extra."** The
base ST ledger is therefore NOT a compromise: tester + 24-pin + EPS +
one-of-{PCIe, 12VHPWR} = 4/4 ports, with the GPU-power module swapped per
DUT era — a natural shop workflow (the §12 field-kit/blade swap is the
mechanism). §12a's remaining value: BOTH GPU modules docked at once (no
swap step), i.e. convenience + a de-facto spare position, not a fix.
Ratification urgency drops accordingly; the 4-module bundle (+~$25–35
landed, $1,399-class) becomes a configurator upsell rather than the
default story.

**Fences:** ST-ONLY (Pro/Max testers keep real ports: streams + µs
excursion bracketing). Header is single-occupancy — a bench that also wants
a NanoKVM on that Hub gives the tester back an RJ-45 port (configurator
note). Zero Hub hardware change; one new JST-PH patch-cable SKU.

**Open before ratification:** UART framing + MARK-relay firmware contract
(new OQ-85 chapter — Hub aux-node driver, relay jitter spec); ping-pong
calibration protocol + a bench item measuring real relay jitter; presence
semantics on the ref pin (tester presents 3.3 V, R21/R22 divider reads it);
deck Hub-bay routing for the PH cable.

## 12b. Hub MEZZANINE as the tester dock — **RATIFIED (owner, 2026-07-16 night: "yes use the mezzanine, that's the cleanest approach")**; supersedes §12a (retired)

**Ratification notes (owner, verbatim intent):** (1) "All hubs will have it
anyway" — NEW OWNER FACT: the Hub-side mezzanine socket becomes STANDARD
FITMENT on hubs (feeds D-3/OQ-77 — the socket is no longer a maybe-SKU
question, at least Standard + Pro). (2) Acknowledged fallbacks when no
mezzanine: tester's own USB direct, or RJ-45 into a hub port. (3) NEW
REQUIREMENT — the tester's exposed RJ-45 must be **PoE-SAFE** (a bench
box with an external RJ-45 invites a network/PoE mis-plug; the consumer
§2.4 no-clamp ruling was for INTERNAL interfaces). ANSWER (better way =
don't invent): adopt the ENT mis-plug fail-safe chain VERBATIM
(REQ-MOD-COMMON-053 / survey 11: SS110 series + SMAJ58A + TPS26621 60 V
auto-retry eFuse + DETECT series R + pin-7 conditioning, ≈ +$2.7) —
designed exactly for 57 V PoE-class injection; CAN pins are covered by
the TJA1051's own bus-pin tolerance (the §2.4 rationale); pins 4/5 are
terminated at ST. Platform pinout stays identical — protection, not
divergence.


**The idea:** the tester deck's Hub bay presents the OQ-77 mezzanine
interface (the Hub-side mate of the 24-pin rev3 J6 stack header) — the Hub
STACKS onto the deck exactly as the stacked SKU stacks onto a 24-pin
module. The deck plays the 24-pin's mezzanine role.

**Why it beats §12a everywhere (J6 as-built facts, atx-24pin review §1):**
the J6 map carries a FULL module port — CAN + DETECT (pin 11) + **STREAM_P/N
(pins 8/9, the RS-485 pair)** — PLUS the Hub bulk feed (+5V_SYS pins 1/2/3)
and grounds. So the TESTER rides the mezzanine link as a native CAN node:
**µs MARK timing intact, no relay firmware, no calibration protocol** — and
at Pro tier even the tester's RS-485 STREAM has a path through the stack.
Power topology stays platform-native: the docked 24-pin module's 5VSB
blades route through deck copper to the mezzanine power pins (the §2.7
source relationship, cable-free).

**Across tiers:**
- **ST**: tester on mezzanine + 4 ports = 4 modules (both GPU modules
  docked). The §12a headroom, with zero firmware inventions. [§12a RETIRED
  if this ratifies.]
- **Pro suite**: tester (incl. its RS-485 stream) on mezzanine + all 8
  ports for modules — the §13 W-suite ledger gets its spare ports back
  (flagship W config was tester+7 = exactly full; now 8 module ports free).
- **Max**: J6 carries NO T1 pair (STREAM = RS-485; pin 13 RSVD) — the Max
  tester keeps an RJ-45 port OR a J6 rev adds a T1 pair on RSVD+spare
  [open question].

**The shared-deliverable win:** the Hub-side mezzanine socket does not
exist yet (D-3/OQ-77 fact) — designing it serves BOTH the stacked SKU
(8th-ruling adopted-in-principle, ENT-AIR first) AND every tester deck.
The tester program becomes the reason to build it now.

**Binding gotchas (carry into the socket design):** (1) build the socket
from the **rev3 J6 NETLIST**, not the published doc table — they contradict
(DETECT 11-not-13, +5V_SYS 1/2/3, STREAM 8/9; atx-24pin review §1) — and
the MIRROR GOTCHA applies doubly on the mated pair; (2) Hub Pro carries no
mezzanine provision yet — add the socket to its (unbuilt) board plan, cheap
now; ENT hub is out of scope (different program); (3) mechanical: stacked-
Hub jack orientation vs deck edge + ~8 mm stack height + the ≤76×60 Hub
mount rectangle (D-3 numbers) at the deck drawing; (4) deck power routing:
24-pin blades → mezzanine power pins sized to the Hub trunk class, tester-
PD assist stays the §2.9 third-source option.

**Decision shape for the owner queue:** ratify §12b as the dock
architecture (retiring §12a); fold the socket design into the D-3/OQ-77
decision as its second customer; Max-tier link = port vs J6-rev sub-call.

## 12c. PER-SLOT LOAD CHANNELIZATION + cable-spec fences (owner Q 2026-07-17 — ADOPTED, engineering-forced)

_Owner: "how do we make the 24-pin test its own 12 V at the same time,
but limited so it doesn't exceed the cable spec?" The question caught a
real trap: the README's pooled posture ("any head routes into the same
12 V plane") makes that IMPOSSIBLE — with paralleled cables on one node,
current division is set by cable/connector resistance, not by us; you can
neither fence a cable nor attribute amps to it. Pooling is RETIRED._

**The architecture:** every plugged head's 12 V lands on its OWN slot
node on the deck; bank groups are ASSIGNED to slot nodes by fixed deck
copper. Concurrency is then free (each slot channel runs its own
staircase+vernier setpoint; total PSU 12 V = the sum) and the fence is
physical. Four layers, strongest first:
1. **Wiring IS the limit** — the 24-pin slot node physically reaches only
   its small group set (1+1+2 legs = 8 A staircase; a vernier share fills
   between); no firmware bug can recruit the big ladder into a cable that
   can't carry it.
2. **Per-slot fuse** at ~1.25× the fence (24-pin 12 V: 15 A ATOF class).
3. **Firmware ceiling map** (head type → per-rail max recruit), with one
   principled exception: spec-defined test pulses (e.g. 5VSB 3.5 A/500 ms)
   are allowed to their governing spec's magnitude+duration — the spec
   that defines the test also rated the connector for it.
4. **Measured attribution closes the loop**: the docked CEC 24-pin module
   measures its section's REAL per-rail current (the ecosystem synergy —
   the tester's channel truth comes from the modules in the path);
   firmware trims to measured, and a plane/mis-plug discrepancy alarms.

**Fence table (sustained recruitment ceilings; bars = the ratified
design-basis currents, §2.8 daughterboard math):**

| Head / rail | Circuits × bar | Cable bar | FENCE (recruit ≤) |
|---|---|---|---|
| 24-pin +12 V | 2 × 6 A (ATX bar) | 12 A / 144 W | **10 A** |
| 24-pin +5 V | 5 × 6 A | 30 A | **25 A** |
| 24-pin +3.3 V | 4 × 6 A | 24 A | **20 A** |
| 24-pin 5VSB | 1 × 6 A | 6 A | **5 A** (+3.5 A/500 ms spec pulse) |
| EPS | 4 × ~13 A | ~52 A | **~45 A** |
| PCIe-8pin | 3 × ~13 A | ~39 A | **~35 A** |
| 12VHPWR | 6 × 9.2 A | ~55 A / 600 W class | **~50 A** |

**Honesty notes:** (a) minor rails physically enter ONLY through the
24-pin (no SATA/molex heads in scope), so the v1.1 minor-bank CAPACITY
(5 V 40 A / 3.3 V 38.8 A) deliberately exceeds its recruitable fence —
installed capacity is headroom/future peripheral heads, recruitment is
fenced at the connector bar; (b) an OCP hunt that would need a section to
exceed its cable bar is REFUSED by the fence and the result is flagged
"limited by connector spec" — we never abuse a cable to find a trip point
(big-head channels reach any realistic 12 V OCP without it); (c) per-slot
nodes ALSO fix same-family multi-slot division (2× EPS no longer split
one plane by cable-resistance luck). Group-to-slot assignment maps per
tier fold into the existing Pro/W ladder-pass [wb]; the 05/08 capture
sheets pick up slot-node structure when they resume.

## 13. WORKSTATION tier (~3,000 W) — replaces the 2 kW ballast (owner ruling, 2026-07-16)

**Owner ruling:** *"dip the 2K unit, because that is over a US breaker anyway.
Go big or go home, Max Workstation or Pro Workstation (if Pro tier is doable
and makes sense price wise), ~3000W effective, as workstation grade PSUs of
that price point are becoming mainstream."*

**The breaker logic, spelled out (why the 2 kW half-step was dead anyway):** a
DUT loaded past ~1,800 W already exceeds a US 15 A/120 V branch circuit — any
shop testing above that has a 240 V (or 20 A/120 V) bench drop, and a shop
with a 240 V drop is servicing the real workstation class, not a 2 kW
half-step. Serve the class properly instead. The TESTER itself is unaffected
by the wall question: it stays a SELV, PD-self-powered sink (6 fans ≈ 24 W +
electronics ≈ 20 W — inside one USB-C PD budget); the DUT's mains circuit is
the shop's problem, exactly as at 1600 W.

**Market anchor (checked live 2026-07-16):** ASUS Pro WS Platinum ships
1600/2200/**3000 W** ATX 3.1 workstation PSUs — the 3000 W at ~$1,036 street,
positioned for 4× RTX 5090 / RTX PRO 6000 builds — with Super Flower (2800 W)
and FSP (2500 W) in the same class. A ~$1k, 3 kW, 12V-2x6-native PSU is a
mainstream workstation part now, and nothing on the market load-tests one
ATX-natively. The owner's "becoming mainstream" read checks out.

**What scales (population, not architecture — ONE Workstation chassis
platform, two SKUs, same board set as Pro/Max):**

- **Fixture bay:** **4× 12V-2x6 heads** (the 4-GPU reality) + 2× EPS + 2–3×
  PCIe legacy + 24-pin ≈ 3.5 kW connector capacity, **3.0 kW continuous
  rating** (same capacity-vs-rating convention as Pro's 1600-in-2.0 kW).
- **Load plane:** R-banks → ~120× paralleled 50 W units (~6.0 kW installed at
  the 50 % derate doctrine); verniers 8 → ~13 L2 devices (one per big
  channel); 2× DAC80508 (16 ch); FET extrusion 300 → ~500 mm class (vernier
  share ~600–750 W); SCP crowbars per-rail unchanged in design (+2 blocks for
  the extra 12V-2x6 rails — per-rail energy stays DUT-OCP-bounded, same §3b
  math).
- **Thermal (§4):** ~263 CFM delivered → 6× Arctic S12038-4K, two-lane duct;
  console grows to ~430 × 450 × 170 mm, ~14–16 kg; same IEC 62368 touch-limit
  grille rules; PD self-power still holds.
- **Displays (§5):** main + ~11 bay screens (4 HPWR bays).
- **Excursion honesty at 3 kW (the one real fence — and it surfaces a fence
  Pro already had implicitly):** per-HEAD excursions are FULLY covered on any
  DUT — the matrix points a fast channel at any 12V-2x6/EPS head, and the
  per-connector pulse class doesn't grow with DUT wattage. WHOLE-PSU
  200 %/100 µs needs delta ≈ 100 % of label above the banks' base load: one
  fast channel (~90–100 A ≈ 1.1–1.2 kW delta) covers whole-PSU 200 % on DUTs
  to ~1.1 kW label — true on today's Pro too, now stated; Max-W's TWO
  channels ganged ≈ 2.2–2.4 kW delta → whole-PSU 200 % into the ~2 kW-label
  class. For 10 ms+ excursion steps the R-banks join (ms-class switching) →
  full-3-kW-delta claims live there. 3 kW-label whole-PSU 200 %/100 µs is
  **NOT claimed in v1** (the report prints the coverage explicitly); a third
  fast-channel population could close it later (open question).
- **OPP hunt** extends to ~2.4 kW labels (120–150 % rule); on a 3 kW flagship
  the report prints "OPP not reached ≤3.0 kW" — itself a shop-useful verdict.

**Is Pro Workstation "doable and price-sensible"? YES — recommended.** The
delta over Pro is ~$570 BOM, almost all passive scaling (resistors, +5 FETs,
metal, +2 fans, +3 screens) — zero new engineering beyond the shared W
chassis/thermal platform Max-W needs anyway — and $4,995 fills the
$3,495 ↔ $5,995 ladder gap cleanly. Two SKUs, one platform, population
deltas only: the platform's SKU-ladder pattern.

**First-cut numbers (BOM v1.2 §3c):** Pro-W BOM ≈ $1,635 → landed ≈ $1,945 →
**$4,995 list (2.6×)**; Max-W ≈ $1,955 → landed ≈ $2,325 → **$7,995 list
(3.4×)**. The full ladder: ST-1000 $1,299 / ST-1300 $1,499 / Pro $3,495
(bundle $3,995) / **Pro-W $4,995** / Max $5,995–6,995 / **Max-W $7,995**;
W bundles run +$800–1,500 over tester-only, dominated by the 4×
12VHPWR-module manifest (open question below). Margin honesty: Pro-W's 2.6×
sits below the platform 3× convention but above capital-equipment norms —
same standing owner call as the other tiers; $5,295–5,495 is the 3×-adjacent
alternative if the convention must hold.

**Manifest RULED (owner, 2026-07-16):** the 4× 12VHPWR stack is a
**CONFIGURATOR option, not a fixed bundle manifest** — bundles are built in
the configurator against a PORT LEDGER (below).

**Port-budget reality (owner flag, same message: "4x 12VHPWR + 1x24 pin +
2xEPS … consumes the entire budget of an 8 port hub"):** counted with the
family's built-in cable aggregation — the EPS module senses **2 cables on
one port** (both CPU cables = ONE module) and PCIe-3port senses 3 cables on
one port — the flagship ledger is: tester(1) + 24-pin(1) + EPS(1) + 4×
12VHPWR(4) + PCIe-3port(1) = **8 nodes = Hub Pro exactly full**. It FITS
today, with ZERO headroom (a 4-EPS-cable monster or any 9th node breaks it
— the ST suite runs 4 ports = tester + 3 modules, which the owner ruled
sufficient: PCIe and 12VHPWR are per-DUT alternates, not simultaneous —
"enough slots, just no extra"). The configurator therefore carries the port ledger and
refuses/reshapes past Hub capacity. Three relief valves, cheapest first:

1. **Standalone-USB overflow (zero hardware — exists today):** every module
   already has USB-C + the §6.14 standalone USB-CDC posture, and the OQ-85
   host path is dual-ingest by design. A deck USB hub feeds overflow
   modules straight to the host: right for steady melt-watch/soak monitors
   (1 kHz rings, thermal-scale events, ms-class host alignment); NOT for a
   rail under µs excursion bracketing (no CAN → no MARK stamps). Ledger
   rule: Hub ports go to the rails under active test; passive monitors
   overflow to USB.
2. **CAN-only expansion jacks on the tester deck (RECOMMENDED as a DNP
   provision — "Bench-Unit-LITE," tightly scoped):** CAN is a shared bus —
   2–3 extra RJ-45 jacks on the tester wire onto the same pair through its
   node; the tester reads each jack's DETECT locally (platform ESD cell per
   jack) and reports presence over CAN (module type/tier rides CAN after
   link-up anyway, per OQ-6); per-jack 5VSB is switched + budgeted from the
   tester's PD domain (OQ-2 discipline; the tester's own uplink VCC is
   never back-fed — ORing per the module pattern). Pair 2 stays dark at
   these jacks (melt-watch Standard modules don't stream) — but **MARK µs
   timing is fully preserved** (they are real CAN nodes), which is the
   measurement story the suite sells. ~$3–5 of platform cells; SI rides the
   §3.1 star/stub bench gate (125 k bench rate is forgiving). Streams +
   aggregation stay with the Hub — the deferred Bench-Unit question STAYS
   deferred; this is its cheap probe.
3. **A 12-port bench Hub SKU (real program):** only if the field shows
   workstation suites routinely wanting 9+ full-timing streaming nodes —
   the deferred-variant tripwire is now concrete instead of vibes.

**Bench 5VSB ride-through — COVERED by platform safeguards (owner,
2026-07-16: "not worried … tons of safeguards"):** the latest Hub PCB
already muxes all three 5 V sources (§2.9: MAIN_5V + PSU 5VSB + USB), a
bench Hub sits on host USB anyway, the Standard Hub rides a ~25 ms-class
hold-up cap (persist-contract SPICE table 16–26 ms — comfortably past the
12/17 ms hold-up test windows), and the fault posture is persist-then-die
by design (≤15 ms gasp contract). NEW OWNER FACT recorded same message:
**Pro and Max are planned to carry SUPERCAP hold-up — tens of seconds** —
folded into `firmware/contracts/persist-on-fault.md` (Tier outlook: flips
that tier's persist class from gasp to full-state). The deck 5 V feed is
therefore DOWNGRADED from "required" to an **optional opportunistic tap**
into the Hub mux's third input (harness provision only — extra margin, and
it powers nothing that isn't already tester/deck-powered).

**W-tier open questions:** (a) the whole-PSU-200 % fast-vs-bank split wants
the schematic-pass step-table treatment; (b) W chassis/two-lane-duct quote;
(c) is a third fast-channel population worth offering to close the
3 kW-label 200 % gap? (d) deck length for 4 HPWR slots + expansion-jack DNP
count — coordinate with §12 before the blade-field drawing freezes; (e)
owner pick on relief valve 2 (design the DNP jacks in, or ship
USB-overflow-only).

## 14. "SPECIAL EDITION" — glass shell + full-loop water cooling (owner idea, 2026-07-16 night; **ROADMAP — HALO NORTH STAR**, owner-committed same night: "I genuinely do want to have it")

**Owner (verbatim intent):** "more for flair and because we are a bespoke PC
shop known for extreme water cooling — Special Edition Pro and Max variants
(with the 3000W addon maybe): glass or otherwise clear shell, full loop
watercooling, blocks on the extreme heat points and maybe even sandwiched
around the board too. Not necessarily practical, but it would be *awesome*."

**Three real engineering arguments inside the flair:**
1. **Water ENABLES the glass shell** — the air tester needs 140–263 CFM
   through grilles and can never be sealed/glazed; remove airflow and a
   fully-sealed clear enclosure becomes legitimate (no vents, no dust, no
   fan noise, full board view).
2. **SELV-only internals = the safest water-cooling target that exists**
   (≤12.6 V inside; DUT + mains OUTSIDE the box). A leak is property
   cleanup, not a shock path — an easier story than any water-cooled PC.
3. **At 3 kW (SE-W) water beats air outright**: 263 CFM ducted is loud;
   3 kW @ ΔT10 °C ≈ 4.3 L/min — a D5 loafing. **SE-W = the silent 3 kW
   tester** (a real spec, not decoration). Water-cooled resistive load
   banks are an established industrial pattern.

**Config sketch:** bank cold plate(s) replace the finned tunnel (50 W array
or chassis-mount resistor swap — trade study); L2 vernier/fast FETs on cold
plates (FBSOA margin improves with case temp); board sandwich plates =
aesthetic-legit but KEEP CLEAR of the fast-channel slice (µH budget vs a
coupled metal slab); QUICK-DISCONNECTS as the native interface ("plugs into
your bench loop" — the on-brand move) + optional radiator kit; coolant-loop
interlocks join the existing safety fabric (flow sensor + coolant NTCs on
the de-gate rail, pump tach in POST, derate-on-low-flow, bimetal backstop
unchanged); RGB/coolant show per the shop's craft (SK6812 chain exists).

**Damage (sketch-grade):** +$400–700 BOM (D5 pump/res, custom bank cold
plate = the big custom part, QDCs, fittings, glass/acrylic + frame) →
SE up-tier $1,000–1,500 over the base SKU; built-to-order halo-unit
economics; the unit doubles as a trade-counter demo of the shop's cooling
work.

**RIFF ADDENDUM (owner: "riff on it... commandeer CPU blocks — we dictate
the mount... bling it out," 2026-07-16 night):**
- **Commandeered-block architecture**: load banks become chassis-mounted
  copper PEDESTALS (resistor legs soldered beneath) topped with standard
  CPU mounting fields (LGA1700/AM5 hole patterns) — any premium retail
  block bolts on; SE-W = six ~500 W "sockets." Pedestals torque against the
  chassis plate, power via bus bars → ZERO PCB mounting stress (we dictate
  the mount, so we delete the mounting problem).
- **THE SLEEPER — thermal-test-vehicle mode**: bank-switch granularity =
  programmable SPATIAL heat patterns per pedestal (center/edge/corner
  hotspot emulation = a die simulator); loop in/out NTCs + flow turbine
  (needed for interlocks anyway) → repeatable per-block CoP curves on the
  CEC_MARK timeline. The SE is secretly a WATERBLOCK TEST BENCH — shop
  content, review-lab sales (TTV buyers), a wedge nobody in the PSU-tester
  or load-bank world occupies. Needs ONE calibration story: factory-
  characterized pedestal thermal resistance (we control the whole stack).
  OWNER POSTURE (same night, superseding sequence): demand unproven →
  side-effect only; THEN owner direction "I would rather make a TTV
  separate SKU" → TTV graduates to ITS OWN exploration
  (`docs/ttv-sku-exploration-2026-07-16.md`: flaw→feature map from the
  owner's critique of existing methods, trace-replay killer feature,
  demand-validation gate). The SE keeps at most DEMO firmware of TTV
  behavior; no tester-side investment beyond that.
- **Partner co-brand numbered runs**: each block house supplies its block +
  co-marketing (custom FET-rail block = the partner canvas; CPU-pattern
  pedestals stay universal so owners re-block at will — which demos TTV).
- **Bling with our own silicon**: lighting brain = the ARGB Standard module
  (spec §7 — dogfoods a second platform product); light-as-instrumentation
  (idle breathe / ARM amber sweep / RUN load-proportional color ramp /
  pass green wave / SCP red strobe latched). Hardline runs, dual D5s,
  edge-lit logo res, mirror-nickel sandwich plates w/ edge glow, anodized
  QDC manifold w/ visible flow turbine, shop coolant dye.
- **Keeps**: non-conductive coolant (shop practice), QDC + drain service
  path, glass = built-to-order crating/mass, plates clear of the fast
  channel, TTV factory pedestal calibration.

**§14a SE LOOP ARCHITECTURE v0 (owner Q&A round, same night):**
- **TWO-CHAMBER: Wet Gallery + Dry Deck.** Sealed zero-airflow glass gallery
  (pedestals/blocks, hardline, res centerpiece, D5s, bay LCDs) + rear utility
  deck where a full-height VERTICAL RADIATOR WALL is the hot/cool boundary
  (owner's "between hot and cool" made structural): rear intake → electronics
  in coolest air → radiator → exhaust. Ubiquiti posture: pristine face,
  utility hidden behind the wall.
- **RADIATOR MATH + POWER-TIERED HYBRID:** ~150 W/120 mm section civilized,
  ~250 W/section warm-coolant (45–50 °C OK; box is a heater → condensation
  nonexistent). 1.6 kW ≈ 11+ sections, 3 kW ≈ 20+ → internal-only full power
  = loud. ARCHITECTURE: internal wall (~2×480 class) = "glass-only mode"
  ~800 W silent; **QDC panel → external MO-RA kit or the shop bench loop =
  full-send 1.6–3 kW**; FIRMWARE COOLANT-TEMP GOVERNOR maps available
  cooling → available test wattage, displayed live ("bring your loop" =
  the buyer's cooling raises the rating).
- **PLUMBING:** flat-face non-spill QDCs (external unlock + PER-PEDESTAL
  service branches off a parallel manifold — swap one block, no drain);
  lowest-point guarded rear drain valve; res-top fill + high-point bleed;
  **firmware DRAIN-ASSIST** (pump pulses w/ load de-gated, on-screen guide);
  res = front-center edge-lit cylinder w/ visible return waterfall, dual
  D5s in machined top, sight-glass + optical level-low into POST.
- **INTERLOCKS (join the de-gate rail):** gallery-floor leak rope, coolant
  ΔT/flow plausibility, level-low, pump tach; POST refuses a sick loop.
  All-copper/brass/nickel, no aluminum; ship DRY + white-glove first fill.
- **UBIQUITI LAYER (SE trim):** main screen → 5–7″ IPS touch face with
  three moods (ATTRACT brand-animation + stats / TEST dense dashboard w/
  wattage dial, per-rail strip, coolant in-out, flow, live °C/W, progress
  ring / FAULT plain-language full-red); dry-deck service screen (drain
  assist); ARGB scenes: flow-synced tube chase, radiator-wall blue→warm
  gradient tracking real ΔT, load-proportional gallery color, SCP =
  lightning flash → latched red; anodized frame, hidden fasteners, bus
  bars under the floor plate (no visible wiring in the gallery).

**Open (before this leaves PROPOSED):** bank cold-plate trade study
(array-on-plate vs chassis-mount resistors); leak-vs-electronics zoning in
the shell; condensation non-issue confirm (loop runs above dew point — it
is a heater); glass vs polycarbonate (thermal + shatter + cost); loop spec
per tier (Pro/Max 1.6 kW vs SE-W 3 kW radiator area); whether SE replaces
or accompanies the fan bank (redundancy vs purity); certification posture
unchanged-check (still SELV, still unintentional radiator).

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
8. **Standard tester sign-offs** (§11): the integrated-instrumentation
   carve-out (bends actuator-not-instrument at ST tier — owner), station
   pricing posture (2× multiple vs 3× convention), plate variant (fewer
   PCIe positions?), and folding the un-shelving into the canonical §6
   ruling record at the Task-13-class pass.
9. **SCP crowbar sizing pass** (§3b): FET ∥-count + fuse time-current pick vs
   the biggest single-rail DUT class (150 A OCP assumption to verify), TVS
   energy rating, release-di/dt value.
9. **Station topology (OWNER: "needs in-field testing" — deliberately
   unresolved):** DEFAULT = this REV B suite (Hub + modules + tester-as-
   module). DEFERRED VARIANT = the REV A "Bench Unit" consolidation (tester
   absorbs the Hub role: port VCC/DETECT/CAN termination + RS-485/T1
   ingest — the hardware sketch for it lives in this doc's git history at
   the REV A commit). Owner's lean: consolidation "feels clumsy"; decide
   from field feedback, not architecture taste.
10. **Workstation tier open set (§13):** W bundle module manifest (4× HPWR
    modules vs 2× + move-them), whole-PSU-200 % fast-vs-bank step table, W
    chassis/two-lane-duct quote, third-fast-channel population option, deck
    length for 4 HPWR slots (coordinate with §12).
11. **Display subsystem details (§5):** exact LCSC panel MPNs (main 2.8″ +
    bay 1.54″ IPS SPI module class) + bezel/harness mechanicals at the
    chassis quote; logo splash asset; bay-screen↔slot mapping when the deck
    drawing lands.
