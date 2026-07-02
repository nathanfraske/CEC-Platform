# FMEA — EPS 8-pin module (`fmea-template-eps`)

Instantiated from `fmea-template-common.md`. Family: EPS 8-pin per-cable
interposer (modules/eps-8pin, rev2 current), 2 cables populated. Sensing:
INA238 per cable + the ENT §6.13-class transient-detection front-end.
Qualitative FMEA only — FMEDA deferred per the common template's depth ruling.

## In-path elements (pre-seeded)

| Ref | Element | Cable | Value/MPN | Package |
|---|---|---|---|---|
| RS1 | Shunt, cable 1 | 1 | Bourns CSS2H-2512R-L500F, 0.5 mΩ (OQ-11 sheet selection) | 2512, 2-terminal, hand-routed Kelvin taps |
| RS2 | Shunt, cable 2 | 2 | Bourns CSS2H-2512R-L500F, 0.5 mΩ (OQ-11 sheet selection) | 2512, 2-terminal, hand-routed Kelvin taps |
| J_IN1 / J_OUT1 | PSU-side in / load-side out, cable 1 | 1 | Molex Mini-Fit Jr 87427-0802, 2x4 | THT header, pegless RA |
| J_IN2 / J_OUT2 | PSU-side in / load-side out, cable 2 | 2 | Molex Mini-Fit Jr 87427-0802, 2x4 | THT header, pegless RA |
| PCB copper | Bundled-shunt vertical transition, per cable | both | — | OQ-10 (copper coin vs. filled-via field vs. plated slot) unresolved for this family |

## Failure-mode rows

| Failure mode | Effect on monitored power path | Detection surface | In-path element | Severity | Fault-injection evidence ref |
|---|---|---|---|---|---|
| Shunt open (RS1 or RS2) | Cable interrupted downstream — direct pass-through failure on that cable only (other cable unaffected, confirming per-cable isolation) | ALERT/threshold (INA238 sudden zero-current) | RS1, RS2 | S3 | TBD — not yet run |
| Shunt short/solder-bridge | None on pass-through current; destroys Kelvin sensing on that cable | INA238 differential reads near-zero permanently; sensor-fault classification | RS1, RS2 | S1 | TBD — not yet run |
| Kelvin tap trace open (hand-routed, §6.8) | None on pass-through (Kelvin taps are off the main current path by construction) | INA238 reads open/rail-clamped input — distinguishable from a true shunt fault if firmware checks tap continuity separately | RS1/RS2 Kelvin taps | S1 | TBD — not yet run |
| Bundled-shunt vertical transition failure (via-field/coin fatigue under 40–55A sustained per §6.4) | Localized resistance rise or open at the vertical, potentially cable-interrupting at the extreme | Rail-voltage sag, ALERT threshold, or thermal imaging during bench (no on-board NTC for this family currently) | PCB copper (OQ-10 pending) | S2/S3 depending on extent | TBD — needs OQ-10 resolution + dedicated thermal/current-cycling bench |
| J_IN/J_OUT connector pin fret | Localized derate, not full interruption for a single-pin fret (8-circuit header spreads current) | Rail-voltage sag under load; thermal imaging | J_IN1/2, J_OUT1/2 | S2 | `bench-misplug-injection.md` (connector-stress leg, once run) |
| §6.13 transient-detection front-end (INA181/comparator) fault | None on pass-through — front-end taps the shunt, does not sit in series | Loss of transient-FREEZE capability (a detection-surface degradation, not a power-path fault) | INA181-class CSA, comparator (if this family carries the ENT §6.13 front-end) | S1 | TBD — not yet run |
| RJ-45 link severed / mis-plug | None on the pass-through cables (module-to-Hub link is electrically separate) | DETECT-code mismatch, CAN bus-state, T1 link state (streaming family per REQ-MOD-COMMON-003) | J5 (RJ-45), D1 (pin-8 ESD) | S1 (by design) | `bench-misplug-injection.md` |

## Fail-passive rows

See `fmea-template-common.md` §"Fail-passive rows" — all five triggers apply
verbatim per cable (2 independent instances); none currently have dedicated
fault-injection evidence (all `TBD`).

## Open findings

- OQ-10 (bundled-shunt vertical) is unresolved; PCB-vertical severity for the
  40–55 A per-cable site cannot be bounded until it closes.
- This is a streaming family (100BASE-T1 per REQ-MOD-COMMON-003) — carries the
  full survey-11 T1 protection network (CMC + ≥100V coupling caps + TVS) as an
  in-path element on pins 4/5, not yet added to this worksheet pending that
  network's BOM landing.
- Shunt MPN (CSS2H-2512R-L500F) is not yet written into
  `modules/eps-8pin/bom/*.csv` per the OQ-11 sheet's own checklist — this
  worksheet's in-path element table is ahead of the BOM; reconcile at the next
  BOM-sourcing pass.
