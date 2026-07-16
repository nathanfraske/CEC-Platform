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
| `tester-pro/` | Pro | P4 + RS-485 + OVP-A + 8 verniers + SCP |
| `tester-max/` | Max | Pro superset + on-board digitizer lane (AD9253+GW5A LVDS must stay short) + T1 PHY |
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
    domain never the load plane.

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
- **Pro**: full §C as written.
- **Max adds**: digitizer lane rules (LVDS class, AFE mux stubs ≤10 mm,
  AGND island policy per the AD9253 DS (grade: -105 recommended post-sourcing, C514281); AFE = ADA4930-1 LFCSP-16 drivers + ADG1408 TSSOP-16 mux (mux BW = confirm-before-lock flag)), T1 PHY cell,
  second slice position, OVP characterization = firmware only.

## I. Open items on this sheet

1. ~~(fill at BOM v1) rows~~ FILLED (sourcing pass 2026-07-16): DAC80508Z
   WQFN-16 3×3; OPA2277UA SOIC-8; TPH2502 SOP-8; CH224K ESSOP-10; THVD1450
   SOIC-8; TPS55288 VQFN-26-HR (the in-stock OVP pick); HFD4/5-SR SMD relay;
   ADA4930-1 LFCSP-16; ADG1408 TSSOP-16; 88Q2110 QFN-40. Supply-risk
   register: BOM doc §5 (P4 OOS = risk #1).
2. Bank step ladder + leg fusing table (sketch §9.1) → freezes §C.12
   quantities.
3. Slice bus geometry study (the µH budget worked example) before the
   prototype spin.
4. New-checker implementation list (F.5) → scripts/cec_constraints rows.
5. Deck ↔ OQ-89 front-plate geometry co-freeze (sketch §9 item on plate
   mech standard).
