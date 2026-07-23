# FMEA — 12VHPWR Standard module (`fmea-template-12vhpwr`)

Instantiated from `fmea-template-common.md`. Family: 12VHPWR Standard, 6x
per-pin interposer (beta/12vhpwr-standard, routed/fab-direction per CLAUDE.md
action item 4). Sensing: 6x INA240 per-pin current-sense + 47k/10k rail-voltage
divider. Qualitative FMEA only — FMEDA deferred per the common template's depth
ruling; this family is the furthest along toward FMEDA-readiness since its
shunt part is already sourced and its production thermal pass is done (below).

## In-path elements (pre-seeded)

| Ref | Element | Pin | Value/MPN | Package |
|---|---|---|---|---|
| RS1–RS6 | Per-pin shunt | 1–6 | Bourns CSS2H-2512R-1L00F, 1 mΩ — LCSC C4175647, already sourced (OQ-11 sheet confirms this is the only real 1.00 mΩ part; spec's `-K-1L00F` citation is a documentation erratum, not this BOM) | 2512, 2-terminal, hand-routed Kelvin taps |
| J3 | PSU-side input connector | all 6 | Molex 219116 / 2191161161, 12V-2x6 board-mount male header | THT, right-angle, board-mounted (no detachable bridging cable, §2.8 LOCKED) |
| J4 | Load-side output pigtail | all 6 | Molex 12V-2x6, captive soldered pigtail to GPU | Soldered cable, no mated connector pair on this end |
| PCB copper | Per-pin fan-out lanes + F/B transition vias | 1–6 | — | Production rev residual per CLAUDE.md item 4: single-layer-per-segment (HI F.Cu / LO B.Cu), F→B transition vias 0.6/0.3mm (below the Power12V netclass 0.9/0.5mm spec) — proto-clean, production-rev margin item |
| TH1/TH2 | Board/ambient NTC (not in-path, but the family's only temperature datum per CLAUDE.md — noted for detection-surface completeness) | — | Murata NCP15XH103F03RC, LCSC C77131 | 0402 |

## Failure-mode rows

| Failure mode | Effect on monitored power path | Detection surface | In-path element | Severity | Fault-injection evidence ref |
|---|---|---|---|---|---|
| Shunt open (any of RS1–RS6) | That pin's lane interrupted — direct pass-through failure on that pin only (per-pin isolation; other 5 pins unaffected) | ALERT/threshold (INA240 sudden zero-current on that channel) | RS1–RS6 | S3 | TBD — not yet run |
| Shunt short/solder-bridge | None on pass-through current; destroys sensing on that pin only | INA240 differential reads near-zero permanently; sensor-fault classification | RS1–RS6 | S1 | TBD — not yet run |
| Kelvin tap trace open | None on pass-through (off main current path by construction) | INA240 reads open/rail-clamped input | RS1–RS6 Kelvin taps | S1 | TBD — not yet run |
| F→B transition via fatigue/crack under sustained current (0.6/0.3mm vias, below netclass spec per production-rev note) | Localized resistance rise; a sustained 12A single-pin-hog condition already measured (2026-06-09 FEM probe) to run the hog lane's transition to ~J 85 A/mm² — ~15% under the sustained ceiling, i.e. thin margin, not yet a fault | Electrical (INA240 imbalance-across-pins signature — the "58% instant electrical outlier vs. lagging ~2.2°C shunt thermal asymmetry" detection thesis already confirmed by the FEM probe) + thermal (TH1 near-shunt) | PCB copper (F→B vias) | S2 (approaches S3 margin under sustained imbalance — flagged, not yet a violation) | 2026-06-09 FEM probe (analytic, not physical injection — physical bench still `TBD`) |
| J3 connector pin fret (12V-2x6 board-mount header) | Localized derate on the affected pin(s); a sustained pin-current imbalance (the "12A hog" scenario) is the family's own documented worst case | Rail-voltage sag / INA240 imbalance signature | J3 | S2 | `bench-misplug-injection.md` (connector-stress leg, once run) — distinct from the FEM-probe imbalance finding above, which is a design-margin analysis, not a fault-injection result |
| J4 pigtail solder-joint fatigue (no mated pair on this end, captive cable) | Localized derate or open on one pin's lane at the load end | Rail-voltage sag / INA240 zero-current on that channel, same signature as a shunt open | J4 | S2/S3 depending on extent | TBD — not yet run |
| RJ-45 link severed / mis-plug | None on the pass-through 12V-2x6 path (module-to-Hub link is electrically separate) | DETECT-code mismatch, CAN bus-state | RJ-45 jack (FTP, cec:RJ45_FTP_Shielded_Horizontal), pin-8 ESD diode | S1 (by design) | `bench-misplug-injection.md` |

## Fail-passive rows

See `fmea-template-common.md` §"Fail-passive rows" — all five triggers apply
verbatim per pin (6 independent instances); none currently have dedicated
fault-injection evidence (all `TBD`).

## Production thermal margin (REQ-MOD-COMMON-032 — already partially answered)

Per CLAUDE.md action item 4: re-validated 2026-06-24 with the 2.5D min-cut
solver + production case-cooling (metal case, TIM on RS1–RS6 + M3 mounts) =
maxT 72.95 °C / dT 22.95 °C = PASS at balanced 600 W/50 A. Still-air no-case
bound (conservative number, per the 12VHPWR precedent this REQ names) = maxT
151 °C / dT 101 °C. This is the family furthest along toward closing
REQ-MOD-COMMON-032; the residual items are the production-rev margin note above
(single-layer lanes, undersized transition vias), not open unknowns.

## Open findings

- F→B transition via undersizing is a real, named production-rev item (not
  hypothetical) — carries the highest-confidence S2-approaching-S3 severity of
  any row across all four families precisely because it already has FEM
  evidence, unlike the other families' `TBD` rows.
- Spec-text erratum (`CSS2H-2512K-1L00F` should read `-R-1L00F` at spec lines
  ~511/625/836/1351) does not affect this BOM (already correct) but should be
  folded into the pending v1.2.0 spec edit per the OQ-11 sheet's checklist.
