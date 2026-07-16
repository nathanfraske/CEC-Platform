# PSU tester board family — exhaustive design sheet (pipeline input)

STATUS: DRAFT v0 (2026-07-16). The design contract for every board under
`testers/` — floorplan zones, per-component placement rules, routing
standards, stackup, and the gates the platform pipeline enforces. Package-
specific rows marked **(fill at BOM v1)** complete when the sourcing agents'
results integrate into `docs/psu-tester-bom-draft-2026-07-16.md`. Design
basis of record: `docs/psu-tester-exploration-2026-07-14.md` (+§6 ruling),
`docs/psu-tester-architecture-sketch-2026-07-16.md` (REV B + §3b/3c/3d/§10–12),
`docs/psu-tester-component-research-2026-07-16.md`. Nothing here alters a
LOCKED platform decision; the blade interface rules inherit §2.8/iteration-7
verbatim.

## A. Board census (who exists and why)

| Board | Tiers | Why it is its own board |
|---|---|---|
| `tester-standard/` | ST-1000/1300 (population variants, same copper) | C6-class control, no fast channel/OVP/streams — different compute + loop count than Pro |
| `tester-pro/` | Pro + **Pro-W** (~3 kW population variant, §H) | P4 + RS-485 + OVP-A + 8 verniers + SCP |
| `tester-max/` | Max + **Max-W** (~3 kW population variant, §H) | Pro superset + on-board digitizer lane (AD9253+GW5A LVDS must stay short) + T1 PHY |
| `fast-channel-slice/` | Pro ×1, Max ×2 | The µH-budget lives at the fixture — the slice's copper IS the circuit; separable bench-gate prototype |
| `slot-deck/` | all | Thick-copper blade fields + load-bus routing + Hub bay; mechanically chassis-bound, revs with fixture geometry not electronics |
| `hpwr-fixture-head/` | all | The per-test wear position; replaceable by design |

AC sense pod: PARKED (owner) — no folder until un-parked. R-bank plates:
chassis metalwork + lug wiring, NOT a PCB (bank switching FETs/fuses live on
the main board; only heavy wire crosses).

## B. Floorplan doctrine (zones, in airflow order — sketch §4 is binding)

```
MAIN BOARDS (front→back = cold→hot, the airflow path IS the layout):
[Z1 FRONT/COOL ≤45°C] MCU, DAC, op-amp loop fronts, loop shunts, USB-C+PD,
                       CAN/RS-485/T1, trip comparators, OVP stage, aux bucks
[Z2 FET ROW]           vernier L2 devices ON the extrusion edge (board edge-
                       mounted TO-247/264 row), gate networks + NTCs at pins
[Z3 BANK SWITCHING]    bank NFETs + fuses at the rear edge, lug fields to the
                       chassis R-plates; SCP crowbar blocks at their fixture
                       feeds (electrically Z3, physically at the front bus —
                       see C rules)
[Z-BUS]                the heavy load return bus bar / pour spine runs the
                       board spine; STAR GROUND at its single tie point
```

- Zone boundaries are keepout-enforced in the pipeline (corridor keepouts,
  same mechanism as the module high-current corridors).
- The slot deck sits ABOVE the main board plane (chassis standoffs); heavy
  interconnect = bolted bus/lug or blade-class joints, never board-to-board
  headers carrying load current.
- Thermal gradient rule: nothing precision (shunts, references, DAC) may sit
  downstream of Z2 in the airstream (sketch §4 precision-zone rule).

## C. Per-component placement rules (the exhaustive list)

Format: component → board/zone → rule → why → how the pipeline checks it.

**Control plane**
1. **MCU (C6 on ST / P4 on Pro/Max)** → Z1, within 50 mm of USB-C and the
   CAN jack; crystal per Espressif keepout; NO antenna keepout (wired
   product, platform beta precedent W9). Check: courtyard + net-length lint.
2. **Setpoint DAC (DAC80508-class)** → Z1, SPI run ≤60 mm to MCU, its 8 ref
   outputs fan TOWARD the FET row so每 loop's ref trace crosses no load
   copper; internal-ref part = keep 10 mm from any >1 W dissipator. Check:
   ref-trace-crosses-load-pour lint (new corpus row).
3. **CC op-amps (one per loop)** → AT their L2 FET, gate trace ≤15 mm with
   series R at the op-amp pin; comp network (series-R + integrator C +
   snubber) placed before autorouting as a rigid cluster. Check: gate-length
   rule per netclass + cluster verify (auto_cluster ownership).
4. **Trip comparators (INA181+TLV7011, §6.13 pattern)** → Z1 at their loop
   shunt's sense pair terminus; identical layout stamp per channel (copy the
   module §6.13 cell — same corpus rules apply verbatim). Check: existing
   §6.13 checkers.
5. **USB-C + PD sink** → Z1 rear-panel edge (rear I/O per sketch §5), USBLC6
   at the connector, CC lines ≤20 mm to sink ctrl; VBUS path fused. Check:
   platform USB cell rules.
6. **CAN (TJA1051) + RJ-45 + DETECT** → Z1 deck-edge; the platform module
   cell verbatim (PESD on DETECT, 2.2 k/4.7 k/10 k per tier). Check:
   existing detect-resistor-code + ESD checkers.
7. **RS-485 TX (Pro) / T1 PHY (Max)** → Z1 beside the RJ-45; pair 2/pair 4
   wiring per the locked pin table; T1 PHY needs its magnetics/termination
   per DS **(fill at BOM v1)**. Check: pin-allocation conformance suite.
8. **OVP-A stage (TPS55289 + relays)** → Z1, its inductor loop tight per DS,
   ≥15 mm from AFE/analog front ends (switching noise), output through
   rail-select relays + series protection to the 24-pin group bus. Check:
   switcher-to-analog spacing lint (new row).
9. **Aux bucks** → Z1 corner, same spacing rule as 8.

**Load plane**
10. **Vernier L2 FETs** → Z2 row, uniform pitch, tab-out to the extrusion
    (edge-mount), source ballast R AT the source pin, per-device NTC within
    5 mm of the tab, gate pull-down at the gate pin, de-gate rail daisy.
    Matched ballast + matched source-trace lengths across paralleled devices
    (Array 3711A precedent). Check: per-device NTC presence + ballast-match
    lint (new rows); thermal via/pour rules via electrothermal gate.
11. **Loop shunts (Kelvin)** → Z1/Z2 boundary, upstream of FET heat in the
    airstream; four-wire: sense pair taps the INNER pad edges, routed as a
    pair, zero load current on sense traces (the platform §6.8/corpus
    kelvin-sense-from-inner-pad rules verbatim). Check: existing Kelvin gate.
12. **Bank-switch NFETs + fuses** → Z3 rear edge at the lug field; fuse
    UPSTREAM of FET; gate lines from MCU cross no load pour (route the
    band-crossing on the foreign layer — cable-board corridor lever).
    Check: corridor keepouts + pour-integrity checker.
13. **SCP crowbar blocks** → physically AT each fixture feed (front bus),
    the loop fixture→FET→surge-shunt→return minimized (<40 mm loop); TVS
    directly across the FET stack; time-fuse in the block. Check: loop-area
    lint (new row) + pour cross-section gate.
14. **Star ground** → ONE tie point where control ground meets the load
    return bus; every sense/control return reaches it without sharing load
    copper. Check: star-point assertion (new checker — single junction net
    topology on the return net).

**Fast-channel slice (its own board)**
15. Bus first: fixture tabs → FET drains → shunt → return in ONE straight
    ≤30 mm heavy path, both layers mirrored + stitched; the loop area sets
    the µH budget (5 V/µH at 5 A/µs — sketch §2). NO vias in the pulse path
    on the current spine (layer mirror carries redundancy instead).
16. Gate stage adjacent to FET row (≤10 mm), slew shaper adjacent to gate
    stage; level-DAC ref enters on a guarded trace; fast comparator at the
    shunt sense pair. Kelvin discipline as rule 11.
17. Slice-to-main signals (gate cmd, DAC ref, comparator out, NTC) cross on
    a shielded/grounded flex or pin header AWAY from the bus loop.

**Slot deck**
18. Blade fields: per-family patterns from `pcb_placement()` EXACTLY (the
    authoritative mating drawings); J_SIG 1×4 socket at the 24-pin field per
    D.6 map (1=-12V, 2=PS_ON#, 3=PWR_OK, 4=GND). Check: EXTEND
    `check_output_daughterboards.py` to the deck (per-family congruence +
    cross-family keying non-seat proof, including deck rotations).
19. Deck copper: per-field fan-out to the load bus sized by the ratified
    joint currents (18.32 A/joint design point) — pour cross-section gate at
    every field. 12VHPWR position = tray + head board, no blade field.
20. Hub bay + RJ-45 channel positions are mechanical routing features —
    document in deck README; no electrical rule beyond keepouts.

**Thermal/protection hardware**
21. NTCs: platform NCP15XH103 cell; one per L2 device + one per SCP block +
    board ambient. Bimetal 120 °C switches: chassis plate items wired into
    the de-gate rail (harness, not PCB) — the de-gate rail itself is a
    board net: route as a protected class, pull-downs at every gate driver.
22. Fan headers: rear edge, tach lines to MCU; fan power from the PD/aux
    domain never the load plane. Fan SKU RULED (owner 2026-07-16): Arctic
    S12038-4K, 4-pin PWM, 12 V/0.33 A class off a TPS54331 aux rail (6× on W
    = 2 A — one buck, sized). 38 mm depth owned by the chassis duct drawing.

**Row construction — the zero-jumper doctrine (2026-07-16 night, owner "giant
mess of wires" challenge)**
22b. **Bank legs get NO discrete wires.** Each resistor row mounts its plate
    with two shared conductors running the row — feed + return — as copper
    flat stock, OR (preferred) the legs carry FASTON .250″ tabs seating into
    receptacles on the slice PCB along the row (the platform's ratified
    blade class, loafing at 2 A/leg vs its 22.9 A rating) → zero wires per
    leg + tool-less leg replacement. Group switching happens on the slice
    between the row pour and the return bar. Per plate assembly: exactly
    THREE connections (feed tap, return tap, one keyed control harness).
    Feed/return bars run as a LAMINATED pair (feed over return, insulated)
    along the duct spine — tidy and low-inductance are the same move.
    Volume basis: legs ARE the duct's finned mass (the resistor field
    REPLACES a radiator; the original "ST-1000 = one double-sided plate"
    claim was pre-math — at real pitch + the ladder-v1.1 overkill minors,
    ST-1000 = THREE plates; full per-model census + fold rules in
    tester-standard/README.md "Field arrangement math v1": 36 mm position
    pitch, 50 mm wall pitch, one row tall always, ST-1000 3×9 / ST-1300
    3×11 / Pro-Max 4×10 / W 6×11 in two lanes ≈ 13 L at 3 kW). Check:
    harness-count lint (≤3 connections/plate assembly) + the §C.21 de-gate
    continuity rule.
    Mechanical stack (owner Q&A 2026-07-16, v2 — the WALL-CARTRIDGE form,
    owner's read): the plate IS the heatsink AND the duct wall. Resistors
    mount in BACK-TO-BACK PAIRS, one on each face, sharing through-bolts
    or a tapped plate (an HS-50-class housing is a 50 W part ONLY bolted
    to metal; free-air ~20 W), tabs vertical. THE WALL SLOTS INTO THE DECK
    BOARD: every pair's bottom tab drops past the plate's bottom edge into
    receptacle rows (one per face) on the flat deck/slice PCB below the
    duct floor — the daughterboard iteration-7 geometry (TE 63969-1
    vertical top entry, blade enters edge-wise) scaled from 6–10 blades to
    16–32. Top tabs common onto the wall's feed bar (one bolted drop per
    wall to the laminated spine). STRUCTURE IS NEVER THE BLADES: wall
    weight lands on chassis rails / end flanges + a registration key;
    receptacle float absorbs the row tolerance stack; fan vibration +
    thermal cycling must never work a load-bearing electrical joint. Gang
    seat/unseat at 16–32 blades = hundreds of N, NOT a hand push — the
    queued press-fit + lever de-fit tools are the wall service story. The
    deck PCB (receptacles, leg FETs, fuses, shunts, trip comparators, gate
    drivers, ONE keyed harness) lives under the duct floor, OUT of the hot
    airstream — the split-architecture compartment goal realized. Verniers
    /SCP are NOT cartridges: TO-247s bolt to a plate section with a narrow
    PCB right at their leads (2.54 mm pins; the gate loop wants mm), same
    blades-carry-current-not-structure logic. Deck drafting decides
    full-width deck vs one strip per wall (panel size / service
    granularity).

**Displays (owner add 2026-07-16 — sketch §5)**
23. **Main LCD (2.8″ IPS SPI) + per-bay LCDs (1.54″ IPS SPI)** → main screen
    on the front-panel harness from Z1; bay screens mount at the deck slots
    (header per slot — see slot-deck README) → ONE shared SPI bus (SPI/
    Digital class) + 74HC595 CS fan-out + one shared backlight-PWM rail;
    connectors keyed; harness lengths ≤400 mm at 10–20 MHz SPI (numeric
    repaint only, 5–10 Hz). IPS TFT NOT OLED (static-readout burn-in —
    reliability posture §10). Why: load readout on the box face; unpopulated
    bay = dark/logo. Check: BOM-lint asserts panel MPN + 595 present when
    any bay-LCD header is placed; SPI class length rule on the chain.

**SCP transient class (owner Q 2026-07-16 — docked modules ride every short)**
24. **Modules in the crowbar path: NO continuous-rating change; assert the
    transient class instead** (the platform's transients-as-transients
    doctrine). Envelope of record, 12 V worst case: peak ≈ V/R_loop ≈
    300 A for ~50 µs (cap dump — the crowbar's own deliberate 30–50 mΩ
    surge shunt dominates loop R and caps BOTH phases); sustained ≈
    150–200 A ms-class (min of DUT OCP and the Ohm's-law loop bound) until
    the DUT trips; worst backstop = firmware release at 50–100 ms.
    Verdict math (sketch §3b addendum): every docked family's shunt /
    pins / blades / pour min-cut passes adiabatic I²t with factors of
    margin; the two WARMEST elements are the 24-pin 12 V 2 mΩ shunt
    (~4.5 J @100 ms backstop → tens-of-K element rise) and its 2× Mini-Fit
    pins (~75 A/pin, ~3–5 J/contact) — pass, bench-verified class.
    CHECKS: (a) design-time I²t assertion per docked family vs this
    envelope; (b) bench: CSS2H pulse-curve verify + an SCP-surge leg in
    the OQ-88 soak (N surges → contact-R + shunt-R drift trend); (c)
    firmware MAY tighten the backstop per head class if bench asks; (d)
    contract note (OQ-85 family): module channels SATURATE during the
    surge (INA outputs clip at rail) — the crowbar surge shunt is the
    calibrated surge recorder, module data = event mark + timestamps +
    collapse trace; (e) 5VSB SCP = a supply-swap event for the
    instrumentation stack, carried by the §2.9 three-source mux + hold-up
    (owner-ruled covered; tester PD rail = the standing second source on
    the deck); (f) front-end abs-max vs the release transient (TVS clamps
    fixture-side, PSU caps clamp module-side) — formalize with a measured
    release envelope at tester proto.

**TIM schedule (owner add 2026-07-16 night; Thermal Grizzly sponsorship
available — TG supplies on hand, co-brand coherent for a thermal-audience
product)**
25. Three bolted-joint classes carry SPEC'D TIM + torque (assembly-doc
    lines; interface R enters the §4 extrusion/plate ledger):
    (a) **Bank legs → plate** (~15 cm² shell base, 24 W, up to ~125
    joints at W): thin paste, ~0.2–0.3 g/joint — the spec exists to guard
    the SHELL-FLATNESS LOTTERY (one warped budget shell dry = a point
    contact = the invisible hotspot among 125), not the nominal ~1 K
    dry-vs-pasted delta. Class RULED (owner, 2026-07-16 night): shop-stock
    premium paste bought in bulk (Kryonaut / Kingpin KPX / Arctic MX-7 —
    "we buy by the gallon"); no separate industrial paste line, no retail
    TG purchase. SPONSORED GRAPHITE PADS (KryoSheet/Carbonaut) are
    ACCEPTABLE AT THIS JOINT CLASS ONLY — both sides are grounded metal,
    so electrical conductivity is harmless — and they buy a real service
    win: leg swaps need no re-paste (the pad stays on the plate,
    reusable). If TG hands over sheets, use them here; coverage ≥~60 % of
    the shell base still beats the flatness lottery. ~15 g/unit ST →
    ~35 g/unit W when pasted. The rule-25(b) isolation-site BAN on
    conductive sheets is UNCHANGED.
    (b) **Linear FETs → extrusion — THE load-bearing interface.** Sketch
    §4 budget: Tj ≤125 °C, Tsink ≤80 °C, 100–150 W/device, IXTH75N10L2
    RθJC ≈0.33 K/W ⇒ case-to-sink allowance ≈ 0.1–0.15 K/W TOTAL.
    Electrical isolation is REQUIRED (mixed drain potentials share the
    extrusion) ⇒ the stack is ceramic insulator + QUALITY paste on BOTH
    faces (~0.06–0.12 K/W total — shop-stock Kryonaut/KPX/MX-7 per the
    owner ruling; grams are trivial, ~1 g/unit). Ceramic = AlN REQUIRED
    at the verniers (0.635 mm AlN ≈0.02 K/W over the ~2 cm² tab vs
    alumina ≈0.12 — alumina alone eats the whole budget; alumina OK at
    the low-duty crowbar sites). Commodity sizes: TO-247 22×17×0.635,
    TO-264 22×28×1. One pad + insulating shoulder washer per BIG-linear
    device (verniers + fast FETs only; the mini-loop moved to 25(c)):
    ST ×2 / Pro ×12 / Max ×16 / W ×~19 ($0.3–3/pad class, BOM §3d).
    ONE-PART-PAD LADDER (owner Q 2026-07-16 — why no single insulating
    pad replaces paste+AlN+paste HERE; all case-to-sink, TO-247 area):
    silicone insulator pads (Sil-Pad 400 class) 0.5–1.5 K/W ✗; premium
    BN-filled silicone (Sil-Pad 2000 class, ~3.5 W/mK @0.25 mm) ~0.3–0.5
    ✗; phase-change-on-polyimide (Hi-Flow dielectric class) ~0.3–0.6 ✗;
    mica/Kapton ~0.3–0.4 AND still need grease both faces ✗; ultra-high-k
    gap fillers (17 W/mK Fujipoly XR-m class) ≈0.13 + contact = AT-budget
    marginal but creep under bolt pressure + isolation-rating + $5–15/pc
    → NOT accepted. Physics: in a one-part pad the polymer IS the
    insulation, and polymers top out ~6–17 W/mK vs AlN's ~170 — the
    ceramic is the only insulator thin-and-conductive enough, and a hard
    ceramic's two faces each need paste. PACKAGE-LEVEL ESCAPE (verified):
    the same L2 family ships SOT-227 miniBLOC siblings with FACTORY AlN
    ISOLATION in the package (IXTN200N10L2, 100 V/178 A L2) — isolated
    base bolts bare to the grounded extrusion, ONE paste layer, no
    ceramic, no shoulder washers; ~2–4× device cost [wb price at BOM
    lock]. That and the per-rail-segment alternative below are the two
    ways to kill the sandwich if assembly labor ever outweighs parts —
    silicone insulator pads (0.5–1.5 K/W for TO-247) are PROHIBITED at
    this site, and **KryoSheet/Carbonaut are BANNED at every isolation
    site (electrically conductive graphene/carbon)**. Alternative under
    the same rule: per-rail isolated extrusion segments (device bolts
    bare + paste only, no insulator) — deck-mech drafting may pick it.
    Packaging corollary: the 5VSB mini-CC loop FET must be TO-220/IPAK
    THT (NOT the DPAK loosely stated in the v1.1 note) to reach the
    extrusion like its siblings.
    (c) **SCP crowbar TO-220s + the 5VSB mini-loop TO-220 + bimetal
    switches → plate/extrusion**: ONE-PART silicone insulator pad, NO
    paste (updated per the owner's pad question, 2026-07-16) — these
    sites' budgets are loose (crowbar = ms pulses; mini-loop ≤~8 W
    continuous, where even 1–2 K/W costs ≤16 K), which is exactly the
    duty one-part Sil-Pad-class parts were made for; dropping paste here
    is a pure assembly win. Only the 25(b) big-linear devices carry the
    AlN+paste×2 stack.
    Checks: assembly doc carries torque + TIM part + thickness per joint
    class; §4 ledger uses the spec'd interface R, never a bare-metal
    assumption. Platform echo: the enclosed consumer products already
    model TIM (12VHPWR case-cooling = TIM on shunts + mounts; §6.6
    TIM-baseplate menu) — same sponsorship surface. Deeper TG fits
    (owner-queue): SE halo (blocks/TIM home turf) + TTV SKU (reference-
    TIM characterization; their delid/direct-die line is adjacent to the
    IHS-cap concavity library).

## D. Routing standards (netclass table — seeds .kicad_pro + .kicad_dru)

| Class | Nets | Width / rules |
|---|---|---|
| LoadBus | fixture feeds, bank legs, crowbar paths, slice bus | POURS/bus copper only, never traces; min cross-section per current via the electrothermal gate (2 oz outers); solid (unrelieved) thermal connects; via fields per platform current-via rules (0.5/0.9 mm ≈ 2 A each, counted by the checker) |
| KelvinSense | all *_SENSE± pairs | 0.25 mm matched pairs, inner-pad taps, no load current, length-match ≤5 mm within pair |
| Gate | op-amp→FET gates, de-gate rail | ≤15 mm (main) / ≤10 mm (slice), series R at driver end, no pour crossings on foreign layers |
| Analog | DAC refs, AFE inputs, NTC dividers | guarded, ≥2 mm from any switcher loop, no parallel runs with Gate class >10 mm |
| SPI/Digital | MCU buses | 0.22 mm, ordinary |
| CAN | CAN_H/L | 0.25 mm coupled pair (platform standard) |
| USB | D± | 90 Ω diff, platform cell |
| RS-485 (Pro) | pair | 0.25 mm coupled, 120 Ω-class |
| LVDS (Max) | AD9253→GW5A | 100 Ω diff, intra-pair match ±0.5 mm, inter-pair ±5 mm per AD9253 DS; reference plane unbroken under the lane |
| PD/VBUS | USB power | 1.0 mm min + pour |

DRU seeds: clearance ladder normal (SELV board — 12.6 V max; spacing is
thermal/current-driven, not creepage-driven); pour-integrity +
min-pour-cross-section + kelvin-from-inner-pad checkers armed (they exist);
LVDS lane plane-integrity rule (new, Max only).

## E. Stackup per board

| Board | Stackup |
|---|---|
| Main boards (ST/Pro/Max) | 4L, 2 oz outer / 1 oz inner; In1 = solid GND; In2 = mixed (control power + short signal detours); load copper on BOTH outers mirrored+stitched over its corridors (cable-board doctrine) |
| fast-channel-slice | 2L, 2 oz both sides, mirrored bus |
| slot-deck | 2L 3 oz (or 4L 2 oz if fan-out congestion demands), load pours dominate |
| hpwr-fixture-head | 2L 2 oz |

## F. Pipeline gates (what must pass before any fab)

1. ERC 0 / DRC severity-error 0 (platform CI posture; boards stay DRAFT-
   marked until then — R-03 rule).
2. Kelvin + diff-pair hard gates (cec_score) on every routed candidate;
   route through the tiered pipeline (manager judge — CLAUDE.md GO-AHEAD
   rule), never deterministic-only for judgement.
3. Electrothermal gate (electrothermal_solve): every LoadBus corridor at its
   §8a design current +25 % margin, 40 °C ambient config (sketch §10.4);
   fusing-check on the slice at pulse-average duty.
4. Keying proofs: extended `check_output_daughterboards.py` green on the
   slot deck (congruence + non-seat + J_SIG map).
5. New corpus rows landed WITH TEETH before trusting them (AM-02
   discipline): star-point topology, ballast-match, per-device-NTC, loop-
   area (SCP), switcher-to-analog spacing, ref-crosses-load, LVDS plane
   integrity.
6. Synth-pipeline Stage-1 REQUIREMENTS answers (recorded here so agents
   don't re-ask): wired-only (no antenna keepouts), thermal_env =
   forced-air duct @40 °C, mounts = chassis pattern per board README,
   connector overhang = fixture/deck edges yes, size targets = chassis-
   driven (sketch §5).
7. Bench gates that block fab regardless of CI: fast-channel single-slice
   prototype (canonical §5.3); gang-insertion/tolerance sample (OQ-86
   extension); worst-cable loop-comp matrix (sketch §10.7).

## G. Mechanical/assembly interface rules

- Extrusion mounting pattern + FET tab hardware per the chassis drawing
  (board README owns the hole table); insulated washers: TO-247 (IXTH75N10L2 verniers) + TO-264 (IXTK90N25L2 fast channel) kits — both DigiKey-consigned THT lines.
- R-plate lug fields: M4 lug pads, wire gauge table per bank current.
- Deck standoffs sized against gang-insertion shear; module support rails
  per sketch §12 flag.
- Chassis grounding: M3 pads to chassis at Z1 corners (platform M3 pattern).

## H. Per-board deltas

- **ST**: 4 CC loops (12V/5V/3.3V/5VSB-peak), PWM+RC setpoints (no DAC),
  no OVP/no slice position/no stream silicon; otherwise identical rules.
  Displays kept (main + ~6 bay, §C.23; C6 drives them via the same 595).
- **Pro**: full §C as written.
- **Max adds**: digitizer lane rules (LVDS class, AFE mux stubs ≤10 mm,
  AGND island policy per the AD9253 DS (grade: -105 recommended post-sourcing, C514281); AFE = ADA4930-1 LFCSP-16 drivers + ADG1408 TSSOP-16 mux (mux BW = confirm-before-lock flag)), T1 PHY cell,
  second slice position, OVP characterization = firmware only.
- **Pro-W / Max-W (~3,000 W Workstation, owner 2026-07-16 — sketch §13, BOM
  §3c): POPULATION variants of tester-pro/tester-max, NOT new boards.**
  Design the Pro/Max copper for the W population count from day one: ~13
  vernier loop positions (2× DAC80508 footprints, second DNP on Pro), bank
  switching array sized for ~120× 50 W legs (Pro populates ~64), 4× HPWR
  fixture feed positions (Pro populates 1), extrusion edge sized for the
  ~500 mm class, 6 fan headers (Pro populates 4), 11 bay-LCD CS lines. The
  W chassis (two-lane duct, ~430×450×170) and the W slot-deck length variant
  are the only new mechanical items. Max-W gangs the two fast-channel slice
  positions (whole-PSU 200 % fence per sketch §13). PORT LEDGER (owner flag):
  flagship W suite = 8 CAN nodes = Hub Pro exactly full — carry 2–3 CAN-only
  expansion-jack positions as DNP provision (RJ-45 + DETECT ESD + switched
  5VSB from the PD domain; pair 2 unconnected; owner pick pending, sketch
  §13 relief valve 2), and carry an OPTIONAL deck 5 V tap position to the
  Hub's §2.9 third input (ride-through already covered platform-side: 3-way
  mux + ~25 ms Standard hold-up + planned Pro/Max supercaps — owner
  2026-07-16, sketch §13).

## I. Open items on this sheet

1. ~~(fill at BOM v1) rows~~ FILLED (sourcing pass 2026-07-16): DAC80508Z
   WQFN-16 3×3; OPA2277UA SOIC-8; TPH2502 SOP-8; CH224K ESSOP-10; THVD1450
   SOIC-8; TPS55288 VQFN-26-HR (the in-stock OVP pick); HFD4/5-SR SMD relay;
   ADA4930-1 LFCSP-16; ADG1408 TSSOP-16; 88Q2110 QFN-40. Supply-risk
   register: BOM doc §5 (P4 blip = owner-ruled ride-out 2026-07-16; design
   against v3.x NRW32X).
2. Bank step ladder + leg fusing table (sketch §9.1) → freezes §C.12
   quantities.
3. Slice bus geometry study (the µH budget worked example) before the
   prototype spin.
4. New-checker implementation list (F.5) → scripts/cec_constraints rows.
5. Deck ↔ OQ-89 front-plate geometry co-freeze (sketch §9 item on plate
   mech standard).
