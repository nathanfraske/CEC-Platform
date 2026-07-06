# Thermal wave-1 + daughterboard thermal landing — 2026-07-06

Landing record for the arc the owner GO'd ("scope and implement those thermal
solve capabilities") plus the two in-flight board items that rode with it
(atx24-out-db F1 fix, ENT KVM carrier). Everything below is verified in-repo;
the maps are in `docs/standard-tier-review/thermal-maps/`.

## 1. atx24-out-db — F1 fix LANDED (In2-lane fusing resolved)

The committed iteration-7 board routed the four multi-point bus rails
(+12V/+5V/+3V3/+5VSB) down a shared 0.3 mm × 1 oz **In2 lane corridor**. The
blade-interconnect FEM audit (`blade-interconnect-thermal-2026-07-06.md`, F1)
proved that corridor carries the full rail aggregates and **fuses** (+5 V at
30 A: 384 mV / 11.5 W in one 0.3 mm lane, J ≈ 2900 A/mm² ≈ 7× the fusing gate;
coupled solve ran away to 3766 °C).

**Fix (generator `route_atx24()`):** the lane corridor is replaced by real
**per-rail full-board floods on separate layers** — GND/In1, +12V/In2,
+3V3/B.Cu, +5V/F.Cu (clipped east of pin 23), +5VSB as a B.Cu inter-row zone,
with an F.Cu east limb + 2-via cluster for +3V3's pin-12 escape. All floods use
`ZONE_CONNECTION_FULL` (solid), and each non-GND tab carries a hard leg-pair
bridge (the Ø2.5 THT tab pads' 45° thermal spokes intermittently mis-connected
at regen).

**Verification (DC-IR field solve — the bottleneck-truth leg):**

| Rail | Broken (committed) | Fixed |
|---|---|---|
| +5V @30A | 384 mV, J=2874 A/mm² (fuses) | **62.6 mV, J99.5=259 (peak 382)** |
| +3V3 @24A | 299 mV (9% of a 3.3 V rail) | **12.4 mV, J99.5=67** |
| +12V @12A | 817 mV | **35.8 mV, J99.5=73** |
| GND @72A | — | **13.4 mV, J99.5=156** |
| total joule (cold) | 592 W (runaway) | **3.82 W** |

Gates: ERC 0 error (5 benign PWR_FLAG lib-mismatch warnings), DRC 0/0
severity-error, `check_output_daughterboards.py` 113 OK.

**F1 is resolved.** What remains is **F2** — the still-air *no-sink* coupled
solve gives dT ≈ 397–401 °C (map: `thermal-maps/atx24-out-db-thermal.png`, a
**uniform** field with no fusing lane — the F1-fix signature). F2 is the
board-can't-shed-worst-case-power-in-vacuum bound, **the same modelled red
eps/pcie carry**, NOT a fusing-class defect. Resolution (owner-gated, per the
memo's F2 disposition): a modelled+verified conduction sink (the three brass
blades into the main board + the output pigtail copper + chassis), heavier inner
copper, or an owner-accepted operating-envelope statement — decided on the
OQ-86 soak datum. **The 30 °C gate was NOT relaxed** (ratification boundary).

## 2. eps/pcie-out-db — solid high-current joints (owner observation)

Owner spotted the thermal-relief spokes on the eps/pcie receptacle pads. On a
52 A (eps) / 39 A (pcie) joint the four ~0.5 mm relief spokes **neck the
current** — raising local J and joint resistance for zero benefit on a
hand-assembled THT board. `route_simple()` was on the KiCad default (thermal
relief); it now sets `ZONE_CONNECTION_FULL` on both floods, matching the atx24
F1 rationale.

| Board (52/39 A worst-case, no-sink) | Thermal relief | Solid |
|---|---|---|
| eps-out-db | max_T 285 °C / dT 235 / maxJ 293 | **191 °C / 141 / 169** |
| pcie-out-db | max_T ~167 °C / dT 117 | **120 °C / 70 / maxJ 69** |

≈ −40 % dT on both; the tab pads go from the hottest feature to cool/solid
(maps re-rendered). The residual heat is the board perimeter = the F2 term.
DRC 0/0, checker 113 OK after regen. All three daughterboards now carry solid
high-current joints.

## 3. Thermal wave-1 modules — LANDED + integrated

Four AM-04-disciplined modules (external anchors, teeth tests, cited constants,
UNVERIFIED markers, additive-only), **166/166 thermal-family tests green**:

- `cec_thermal_sources.py` (T0) — beyond-shunt heat inventory (LDO/LED/MCU/amps/
  diodes from the netlist) + absolute-T material-limit gates + emissivity-region
  extraction. Worked runs: Hub 2.628 W, 12vhpwr 0.575 W.
- `cec_thermal_accuracy.py` (T0) — shunt-TCR / thermal-EMF / amp+ref-drift
  accuracy loop consuming solver temperatures.
- `cec_thermal_boundary.py` (T1a) — gray-body radiation, orientation-correct
  natural + forced convection, cable 1D-fin, finite chassis node, solder
  interface-R; 60/60.
- `cec_thermal_scenarios.py` (T1b) — N-1 single-joint-loss sweep, E3
  unequal-sharing (contact-R σ/µ thresholds), partial-seat, I²t, tolerance
  corners, seeded Monte Carlo + sensitivity; 43 tests.

**Integration (coordinator-gated):** two **advisory, fail-safe** analyses added
to `REGISTRY_OPTIONAL` in `cec_synth_pipeline.py` — `THERMAL_SOURCES`
(beyond-shunt inventory) and `THERMAL_CONNECTOR_SCENARIOS` (per-board N-1
verdicts for daughterboard families). Both `binding="advisory"` (never block —
the material/N-1 gates stay owner/soak-gated) and fail-safe (→ [] on any error).
`electrothermal_solve()` and `physics_gates()` are **untouched**, so SB-08 golden
(which calls `electrothermal_solve` directly) and the `test_am04_anchors`
physics tests stay **byte-identical**. No test references `REGISTRY_OPTIONAL`.
Verified: eps-8pin arms THERMAL+THERMAL_SOURCES; atx24-out-db arms
THERMAL+THERMAL_CONNECTOR_SCENARIOS. Wave-2 (transient RC, force-coupled contact,
K1/K2 V&V, per-board accuracy channel maps, a conduction-sink-refined
electrothermal variant) → FOLLOWUPS.md.

### N-1 honest headline (T1b)
The joint counts were sized for **load**, not single-joint-loss survival. Only
pcie survives N-1 within policy (176 % margin, survivor 21.9 °C). atx24 and eps
fail N-1 on every redundant rail (atx24 +5V→52.6 °C; eps→39.3 °C), and atx24
+12V/+5VSB have zero redundancy (single joint = open circuit on loss). E3
unequal-sharing: atx24 GND fails at contact-R spread σ/µ ≈ 0.21, eps ≈ 0.28 —
**these are the OQ-86 bench acceptance criteria** (contact-R spread across the
row, measured at the confirm soak).

## 4. ENT KVM carrier — merge bug fixed, LANDED as DRAFT

The Path-C carrier generator (`gen-ent-kvm-carrier.py`, 125 parts / 10 leaves)
had a **GND↔LT_INT net merge**: in leaf 10, R48 (GND) and R49 (LT_INT) sat on
the same compose row with a GND power stamp between them, and the auto-router's
horizontal stubs overlapped (267.97–270.51 mm @ y 161.29) → the whole 147-node
GND net collapsed into LT_INT. **Fix:** R49 moved one row up (compose y 66→54),
giving LT_INT its own y-line. Result: GND 147 nodes / LT_INT 3 nodes (correct).

Residual ERC = 11, all cosmetic / correct-connectivity: 6× `pin_not_driven` on
MCU-GPIO-driven inputs (U1 GPIO typed bidirectional — every net has its U1
driver on-net), 4× `pin_to_pin` on U7's ganged power-output pins, 1× duplicate
PWR_FLAG. Board is DRAFT (WIP by convention); remaining MAC↔PHY/USB wiring +
PWR_FLAG dedup + PCB layout are the next KVM pass (FOLLOWUPS).
