# Blade-interconnect thermal audit + connector-joint element + full-stack analysis — 2026-07-06

**Owner charter (verbatim):** *"can you go over the FEM suite and make sure it
takes* everything *into consideration? For example, the new blades we have,
does it model out the interconnect between those? Can we do a full stack
analysis of that to make sure the numbers it throws out are correct and gated
in truth?"*

Scope of this pass: `scripts/` + `tests/` + docs. **No `.kicad_*` file was
modified** — boards were read-only inputs. Companion record: fit-memo
addenda 1–10 (`blade-fit-check-2026-07-04.md`) for the joint geometry chain.

---

## 1. Coverage audit — what the suite models vs. what it did not

Suite read end-to-end: `cec_synth_pipeline` physics section (`dt_ipc`,
`_picard_dt`, `_net_currents`, `_min_cut`, `_via_cluster_sizes`,
`electrothermal_solve`, `physics_gates`), `cec_thermal2d` (2.5D coupled
electro-thermal field solve), `cec_dcir` (2.5D DC-IR field solve),
`cec_thermal_overlay`, anchor suites (`test_am04_anchors`,
`test_thermal_gates_corpus`), `am04-microboard/DERIVATION.md`.

**Modelled (before this pass):** board trace/pour copper (serial min-cut +
IPC-2221 Picard, plus the two field solvers for plane-pessimism and neck
refinement), via/PTH barrels (per-transition cluster split analytically; real
barrel segments in the field solvers), shunt I²R with Rth, transient
RMS-over-τ model + fusing-J gates, case-cooling/chassis sinks (12VHPWR,
opt-in knobs in `thermal2d`), per-pin connector contact heat **only** as the
12VHPWR-era `r_contact_mohm` knob (J_IN*/J_OUT* pads, default off, no
truth anchor).

**NOT modelled (the gap list):**

| # | Gap | Status after this pass |
|---|-----|------------------------|
| G1 | **Board-to-board connector joints** — the TE 63951-1 blade / 63969-1 receptacle interconnect: contact interface R, brass (not copper) conduction, joint-to-ambient Rth | **CLOSED** — first-class element, §2 |
| G2 | Solder-tail / fillet resistance at the joint | folded into the element as a parameterized segment (~0.11 mΩ) |
| G3 | Non-copper conductor materials (brass TCR ≠ copper TCR) | CLOSED for joints (per-segment ρ/α); board copper stays Cu — correct |
| G4 | Off-board conductors: Mini-Fit Jr input headers/crimps, 12V-2x6, pigtail wires | OPEN by scope — model boundary is the board edge + declared joints; wires also act as unmodelled HEAT SINKS (conservative direction for board dT, optimistic for nothing) |
| G5 | Joint-row mutual heating (TE's 22.9 A datum is a single-joint bench figure; ten joints at 4.2 mm pitch share air) | OPEN — flagged for the OQ-86 soak; the calibrated Rth is single-joint |
| G6 | Vertical-standing board convection posture (h differs from horizontal ~10–20%) | OPEN — noted as an assumption; inside the model's honesty band |
| G7 | `_net_currents` role model mis-classified **negative rails**: `"-12V"` matched the `"12V"` substring → a 0.3 A ATX signal rail took the 40 A cable current and false-fired the runaway gate | **FIXED** (§3), tested |
| G8 | The three output daughterboards had **never been run through any thermal gate** (their gates were ERC/DRC/netlist/keying; atx24's README carried an explicit "Electrothermal sanity — PENDING (W-item)") | **CLOSED** — §4 full-stack runs; findings F1/F2 |

**AM-04 discipline verified intact:** `test_am04_anchors` ran 8/8 (chart
points, Picard, conservatism, blocking-with-the-mark, corrected composition
on the micro-board) before any edit; 15/15 after (the 7 new joint/fix tests).
`test_thermal_gates_corpus` 18/18 before and after.

## 2. The connector-joint element (implemented, anchored, toothed)

`cec_synth_pipeline` now carries `JointSegment` / `JointSpec` /
`joint_solve` / `joints_solve` + the `joint_te_63951_63969()` factory
(registry `JOINT_SPECS` — future connector classes declare their own spec).

- **Model:** contact interface R (TE 108-1706 spec **≤1 mΩ**, used at max =
  conservative; the published figure already includes some bulk, so summing
  explicit segments double-counts slightly on the safe side) in series with
  brass conductor segments at real geometry — blade 6.35×0.81 × ~12 mm
  (0.149 mΩ), receptacle 7.4×0.41 × ~8 mm (0.169 mΩ), 2 stamped tails +
  solder ~2 mm (0.111 mΩ); ρ_brass 6.4e-8 Ω·m, α 0.0015/K; total 1.43 mΩ at
  20 °C. Self-consistent dT = P(T)·Rth (Picard, contact R held constant —
  its T-dependence is unpublished interface physics).
- **Anchored in truth (AM-04 pattern):** Rth is **not hand-picked** — it is
  calibrated so the model reproduces TE's published rating datum: **22.9 A →
  30 °C rise** (108-1706 Fig 4, derived by AMP 109-45-1 — the *same*
  30 °C-rise method the platform margin policy uses). Calibrated Rth =
  39.4 °C/W. `T12JointRatingAnchor.test_rating_datum_reproduced` asserts it.
- **Worn scenario is a modelled case, not an aside:** `worn=True` swaps the
  contact to 10 mΩ (fretting/degradation class) — the iteration-10
  0.34 W-vs-3.4 W split now flows through the same solve and the same gates.
- **Teeth:** a worn contact at the 18.32 A policy current computes dT
  139 °C and **fails `physics_gates`** ("joint over-temp"); a blade
  cross-section sabotaged to 10 % more-than-doubles dT (both tested).
- **Additive contract:** `ThermalResult.joints` defaults to `[]`;
  `electrothermal_solve` computes joints only when `cfg.params['joints']`
  declares them. Asserted two ways: in-test (a run with joints declared has
  *identical* nets/vias/shunts to one without) and against a **saved
  pre-change baseline** of all three daughterboards — eps/pcie outputs are
  byte-identical; atx24 differs **only** on `/-12V` (the intentional G7 fix).
- `cec_dcir.solve_net`/`_terminals` gained optional `src_refs`/`sink_refs`
  terminal predicates (default = the old J*/RS* rule, unchanged) so
  non-shunt boards (the daughterboards: tabs J10.. → field J1) can be
  field-solved.

## 3. The `-12V` role-model fix (behaviour change, flagged loudly)

`_net_currents` now classifies nets containing `-12V` as a negative rail
(`rail_neg12_A`, default 0.5 A) **before** the `"12V" in name` substring
test that used to hand them the full 40 A cable current. Affected boards:
only those with a −12 V net (the 24-pin main board, the atx24 daughterboard)
— on both, the old number was a false 40 A pessimism (999 °C runaway on a
0.2 mm signal trace). Every other net class is untouched (tested:
`test_neg12_rail_classification_fix`). SB-08 golden (eps-8pin) is unaffected
— no −12 V net, no joints declared; its solver inputs and outputs are
unchanged by construction.

## 4. Full-stack analysis (main-board pour → joint → blade → daughterboard → field)

**Assumptions, stated:** ambient 50 °C (`enclosed_passive`, §6.6 posture);
still air; no conduction sinks (pigtail wires, blade-to-main-board
conduction, chassis strain-relief hardware all unmodelled — every one of
them helps, so board-side numbers are conservative); stackup as built
(1.6 mm, 2 oz outer / 1 oz inner — read from the board files); currents =
the iteration-7 owner design basis (ATX 6 A/circuit bar; EPS 52 A/cable;
PCIe 39 A/cable; per-joint allocations at the ratified counts 10/6-per-cable).
Main-board side: **no clip placement exists yet on any main-board PCB** —
its number below is an assumption-based analytic figure for a local ≥6 mm
2 oz pour per joint at `pcb_placement()` coordinates, to be verified in that
board's own layout pass.

**Per-element results (nominal contact; worn in brackets where it matters):**

| Element | atx24 | eps (per cable) | pcie (per cable) |
|---|---|---|---|
| Main-board local pour @ worst joint (6 mm 2 oz, assumption) | 17.0 °C @18 A single-face; 5.4 °C mirrored | 15 °C class @17.3 A | 8 °C class @13 A |
| **Joint** (TE 63951-1 + 63969-1, calibrated element) | 12V 8.2 / 5V 12.9 / 3V3 8.2 / 5VSB 2.1 / **GND 18.6 °C** [worn 134.5] | **17.3 °C** [worn 124.6] | **9.7 °C** [worn 69.9] |
| Blade conduction (inside the joint element) | 0.15 mΩ of the 1.43 mΩ — minority | same | same |
| **Daughterboard copper — analytic (IPC min-cut)** | +12V/+5V/+3V3 **999 (runaway)** — min-cut 0.0104 mm² = the 0.3 mm 1 oz In2 lane | +12V 22.1 °C; GND 427.9 °C (plane-pessimistic) | +12V 4.6 °C; GND 296.2 °C (plane-pessimistic) |
| Daughterboard — **DC-IR field solve** (bottleneck truth) | +5V **384 mV drop @30 A (11.5 W), J=2874 A/mm²**; +12V 817 mV @12 A; +3V3 299 mV @24 A (9 % of a 3.3 V rail); +5VSB J=575; GND plane 23 mV, J=224 | +12V 5.1 mV, J=69 ✓; GND 16.4 mV, J=157 | +12V 6.7 mV, J=62 ✓; GND 7.6 mV, J=96 ✓ |
| Daughterboard — **2.5D coupled thermal** (mutual heating, ρ(T), nonlinear convection+radiation) | **max_T 3766 °C = model runaway; 592 W** — the lanes fuse open | **dT 216.7 °C** (2.75 W total on an 11.4 cm² still-air board) | **dT 116.8 °C** (1.18 W) |
| Output field / pigtail solder joints | field THT pads into the (broken) lanes | field pads sit in wide pours ✓ | ✓ |
| **Stack's hottest element** | **daughterboard In2 lanes (catastrophic)** | daughterboard copper (board-level, not a neck) | daughterboard copper |
| Margin to 30 °C-rise policy | joints PASS (worst 18.6 = the known 127 % hairline); **board FAILS unboundedly** | joints PASS (17.3); board FAILS in modelled posture (217 vs 30) | joints PASS (9.7); board FAILS in modelled posture (117 vs 30) |
| Worn-contact sensitivity | any joint at 10 mΩ → 60–135 °C rise → gate fires | 125 °C → fires | 70 °C → fires |

### Findings

- **F1 — REAL DEFECT (atx24-out-db, committed board): the four In2 bus
  lanes (0.3 mm × 1 oz, ~57 mm) carry the full rail aggregates (12/30/24/6 A).**
  Field-proven, not an artifact: 384 mV @ 30 A on +5 V alone (11.5 W in one
  lane; J ≈ 2900 A/mm² ≈ 7× the fusing gate), +3V3 loses 9 % of its rail
  voltage, and the coupled solve runs away (the lane fuses). Root cause is
  visible in the board's own README: per-pin stubs were sized ("sub-amp per
  stub" — itself wrong, ATX allows 6 A/pin) and the per-rail aggregate was
  attributed to "the blade-clip joints on the main board", but the aggregate
  must cross the daughterboard's own lane between the tab group and the
  field pins. The electrothermal check was explicitly deferred
  ("PENDING W-item") — this pass executed it; result: **FAIL**. The eps/pcie
  architecture (direct wide F+B pours per polarity) does not have this
  defect — their +12 V is clean in all three solvers.
- **F2 — eps/pcie board-level dissipation vs the tiny still-air board.**
  At the 52/39 A worst-case basis the boards dissipate ~1.1–2.8 W on
  ~11 cm²; the no-sink still-air model gives dT 217/117 °C — over policy.
  Honest framing: the unmodelled sinks are large (three 22.9 A-class brass
  blades conducting into the main board, the soldered output pigtail's
  copper, chassis strain-relief), the basis current is the *worst-case*
  sustained figure, and dT scales ~I²: at a 26 A typical-sustained EPS
  draw the same model gives ~54–71 °C; at 17 A ~24–37 °C. Verdict: **not a
  fusing-class defect but a real gate red** — needs either heavier copper
  (2 oz inners), more spreading area, a modelled+verified conduction sink,
  or an owner-accepted operating-envelope statement. **The OQ-86 thermal
  soak is the decisive datum** (F2 is exactly what a soak measures).
- **F3 — the `-12V` mis-classification** (G7): fixed + tested; retired a
  standing false 999 °C runaway on the 24-pin family solves.
- **F4 — the joints themselves are healthy**: every nominal joint sits
  inside the 30 °C budget with the worst (atx24 GND, 18.6 °C @ 18 A) being
  precisely the ratified 127 % hairline the iteration-7 counts already
  surfaced — the model and the margin arithmetic agree, which is the
  "gated in truth" property the owner asked for.

### What the OQ-86 bench soak should check the model against

At the sample fit-check (63951-1 + 63969-1, single mated joint, still air,
thermocouple on the receptacle body):
- **17.3 A (EPS allocation): expect ≈17 °C rise** (model band ±20 % per the
  AM-04 tolerance convention → 14–21 °C).
- **18.3 A (policy max): expect ≈19 °C** (15–23 °C).
- **22.9 A: expect ≈30 °C** — this replicates TE's own rating point; landing
  far off it invalidates the joint calibration, not just the margin.
- **Contact-R trend across 20 insert/extract cycles + the confirm soak:
  ≤1 mΩ nominal; a reading in the several-mΩ class is the modelled worn
  signature** (10 mΩ → 125–139 °C at policy currents = the failure mode the
  §6.14-era sense-return provision would watch for).
- Row soak (all 6/10 joints powered): quantifies G5 mutual heating vs the
  single-joint calibration.

## 5. Gates (this pass)

- `tests/test_am04_anchors.py`: **15/15** (8 pre-existing unchanged + 7 new:
  rating anchor, policy-point scaling, resistance composition, worn-contact
  teeth, sabotaged-cross teeth, additive contract, −12 V fix).
- `tests/test_thermal_gates_corpus.py`: **18/18** unchanged.
- Additive contract vs saved pre-change baseline: eps/pcie solver outputs
  **identical**; atx24 differs only on `/-12V` (intended, documented).
- SB-08 golden: untouched by construction (no −12 V net, no joints declared
  on eps-8pin; solver code paths otherwise identical) — re-run in-container
  at the next container session per standing practice.
- No `.kicad_*` file modified.

## 6. Disposition / follow-ups

1. **atx24-out-db F1 fix is BOARD WORK (owner-gated regen, next iteration):**
   replace the 0.3 mm In2 lane corridor with real per-rail copper — the
   eps/pcie pattern (per-rail F+B pour bands) or a widened corridor on
   2 oz outers; the descent-phase and via-anti-pad constraints in
   `route_atx24()` must be re-derived. The generator comment already warns
   the two-layer-lane trap; the fix is *wider/outer*, not *more lanes*.
2. **eps/pcie F2**: owner decision — heavier inner copper / area / verified
   sink / envelope statement; gate the choice on the OQ-86 soak datum.
3. G5 (row mutual heating) + G6 (vertical posture) ride the same soak.
4. Wire `cfg.params['joints']` declarations into the daughterboard configs
   at the next regen so `physics()` gates the joints routinely (the element
   is in place; declaring them is one dict per board).
