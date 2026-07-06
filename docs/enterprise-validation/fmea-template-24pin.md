# FMEA — 24-pin ATX module (`fmea-template-24pin`)

Instantiated from `fmea-template-common.md`. Family: 24-pin ATX interposer
(modules/atx-24pin, rev3 current). Sensing: 4x INA228 (12V, 5V, 3V3, 5VSB).
Qualitative FMEA only — FMEDA deferred per the common template's depth ruling.

## In-path elements (pre-seeded)

| Ref | Element | Rail | Value/MPN | Package |
|---|---|---|---|---|
| RS1 | Shunt | 12V | Bourns CSS2H-2512K-2L00F, 2 mΩ | 2512, 2-terminal |
| RS2 | Shunt | 5V | Bourns CSS2H-2512K-2L00F, 2 mΩ | 2512, 2-terminal |
| RS5 | Shunt | 3V3 | Bourns CSS2H-2512K-2L00F, 2 mΩ | 2512, 2-terminal |
| RS6 | Shunt | 5VSB | Vishay WSK2512R0250FEA, 25 mΩ | 2512, 4-terminal Kelvin (non-Bourns; only true-Kelvin part at this value — OQ-11 sheet) |
| J3 | PSU-side input connector | all 4 rails | Molex Mini-Fit Jr 5569, 24-ckt, male, RA | THT header (§2.8 LOCKED) |
| J4 | Motherboard-side output connector | all 4 rails | Molex Mini-Fit Jr 5569, 24-ckt, male, RA | THT header (§2.8 LOCKED) — bridged to the motherboard by a dedicated F-F cable, itself an in-path element pending its own part number |
| PCB copper | Rail traces/pours J3→shunt→J4 | all 4 rails | — | High-current stackup per OQ-12 (L3-rails-with-via-detour vs top-layer-rails — not yet resolved for this family) |

## Failure-mode rows

| Failure mode | Effect on monitored power path | Detection surface | In-path element | Severity | Fault-injection evidence ref |
|---|---|---|---|---|---|
| Shunt open (RS1/RS2/RS5) | Rail interrupted downstream of J3 — direct pass-through failure | ALERT/threshold (sudden zero-current + rail-voltage drop at INA228) | RS1/RS2/RS5 | S3 | TBD — not yet run |
| Shunt open (RS6, 5VSB) | 5VSB interrupted; also removes the Hub's bulk-power source (§2.7 — this module IS the 5VSB feed) | ALERT/threshold + Hub-side loss-of-bulk-power alarm | RS6 | S3 | TBD — not yet run |
| Shunt short/solder-bridge (any rail) | None on the rail itself (shunt is already low-mΩ; a hard short bypasses the sense element without interrupting current) — but destroys sensing on that rail | INA228 reads near-zero differential permanently; flagged as a sensor-fault, not a power-path fault | RS1/RS2/RS5/RS6 | S1 | TBD — not yet run |
| J3/J4 connector pin fret/high-resistance contact | Localized I²R heating, voltage droop under load on the affected pin(s); pass-through continues but derated | Rail-voltage sag at INA228 vs. expected regulation; thermal (no NTC on this family per CLAUDE.md — gap, flag for owner) | J3, J4 | S2 | `bench-misplug-injection.md` (connector-stress leg, once run) |
| PCB copper vertical failure (via-field crack/fatigue under thermal cycling) | Localized resistance rise or open on one rail segment | Rail-voltage sag or ALERT threshold, depending on severity | PCB copper (OQ-12 pending) | S2/S3 depending on extent | TBD — not yet run; needs OQ-12 resolution first |
| RJ-45 link severed / DETECT mis-plug (see `bench-misplug-injection.md`) | None on the ATX pass-through (module-to-Hub link is electrically separate from J3/J4 per §2.7/§2.8) | DETECT-code mismatch, CAN bus-state | J1 (RJ-45), D1 (pin-8 ESD) | S1 (by design — confirms fail-passive isolation) | `bench-misplug-injection.md` |

## Fail-passive rows

See `fmea-template-common.md` §"Fail-passive rows" — all five triggers apply
verbatim; none currently have dedicated fault-injection evidence (all `TBD`).

## Open findings

- No board-level NTC/thermal sensor on this family (unlike 12VHPWR's TH1/TH2) —
  the connector-fret detection surface above relies on rail-voltage sag alone;
  flag for owner whether a thermal tap is warranted at ENT tier.
- OQ-12 (stackup choice) is unresolved for this family; PCB-vertical severity
  cannot be bounded until it closes.
- RS6's 25 mΩ Kelvin part (WSK2512) uses a different footprint from RS1/RS2/RS5
  (Bourns CSS2H-2512) — confirm BOM carries both lands correctly at layout.
