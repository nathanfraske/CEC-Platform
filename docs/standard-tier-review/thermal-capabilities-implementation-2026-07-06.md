# Thermal-solve capabilities — implementation plan of record (2026-07-06)

Owner GO: "let's scope and implement those thermal solve capabilities" — executing the
completeness roadmap (thermal-solve-completeness-2026-07-06.md).

## Scope decision
- WAVE 1 (now, 3 parallel agents, module-isolated): Tier 0 + Tier 1 in full.
- WAVE 2 (after wave 1): transient thermal-RC + load profiles, force-coupled contact
  framework (parameters bench-gated), K1 grid convergence, K2 3D benchmark solver, fatigue.
- DEFERRED (data-gated, in FOLLOWUPS): vendor spring stress-relaxation + fretting data,
  real GPU/CPU current traces (percentile worst-case), fab tolerance capability data,
  PCB electromigration kinetics, asperity contact. Tier-3 full-case CFD = the funded endgame.

## Discipline (every wave-1 module)
- AM-04 pattern: external anchors + teeth tests + additive-only (defaults reproduce current
  behavior EXACTLY — existing suites must stay green untouched).
- OWN-MODULE ISOLATION: each agent writes its own new scripts/cec_thermal_*.py + its own
  tests/test_thermal_*.py; NO edits to cec_synth_pipeline.py / cec_thermal2d.py / existing
  tests (integration hooks land in a final coordinator-reviewed pass).
- UNVERIFIED data is marked, never silently defaulted; every constant cites its source.

## Wave-1 assignments
- T0 `cec_thermal_sources.py` + `cec_thermal_accuracy.py`: full heat-source inventory
  (LDO/LED/MCU/IC dissipation from BOM+datasheets); absolute-T material-limit gates (Tg/UL);
  the instrument-accuracy loop (shunt TCR %-error, thermal-EMF at Kelvin junctions,
  amp/ref drift at local T — consuming solver temperature outputs); emissivity-region
  extraction from board files.
- T1a `cec_thermal_boundary.py`: gray-body radiation term (per-region emissivity, enclosed
  vs open postures); orientation-correct natural-convection correlations (Churchill-Chu
  class) + parametric forced-airflow h sweep; cable 1D-fin boundary at connector joints;
  finite-chassis node; solder interface-R + void derates.
- T1b `cec_thermal_scenarios.py`: N-1 parallel-element loss sweep; unequal-sharing
  resistor-network solve over contact-R distributions (gate at worst-single-pin);
  I2t fault-withstand check; tolerance corner runs (thin copper/plating); Monte Carlo
  margin-confidence wrapper + sensitivity ranking.

Integration pass (coordinator-gated) wires the modules into physics()/physics_gates armed
analyses after all three land + full-suite green.

## Status (2026-07-06 — LANDED)
- T0/T1a/T1b: landed, 166/166 thermal-family tests green.
- Integration: THERMAL_SOURCES + THERMAL_CONNECTOR_SCENARIOS added to REGISTRY_OPTIONAL (advisory, fail-safe); electrothermal_solve/physics_gates UNTOUCHED → SB-08 golden + test_am04_anchors byte-identical. Specialized modules (accuracy channel maps, boundary-refined solve) → Wave-2 (FOLLOWUPS).
- Payoff: atx24-out-db F1 fix verified (DC-IR), eps/pcie solid-joint fix (−40% dT). See thermal-wave1-daughterboard-landing-2026-07-06.md + thermal-maps/.
