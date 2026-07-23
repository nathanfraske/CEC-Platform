# FMEA — PCIe 8-pin module (`fmea-template-pcie`)

Instantiated from `fmea-template-common.md`. Family: PCIe 8-pin per-cable
interposer — two SKUs, 2-port (beta/pcie-8pin-2port) and 3-port
(beta/pcie-8pin-3port), rev2 current. Sensing: INA238 per cable (up to 3
cables). Qualitative FMEA only — FMEDA deferred per the common template's
depth ruling. This worksheet is written generically across both SKUs; the
3-port SKU carries one additional cable row (RS3/J_IN3/J_OUT3) that the
2-port SKU omits.

## In-path elements (pre-seeded)

| Ref | Element | Cable | Value/MPN | Package |
|---|---|---|---|---|
| RS1 | Shunt, cable 1 | 1 | Bourns CSS2H-2512R-L500F, 0.5 mΩ (OQ-11 sheet selection, same value as EPS) | 2512, 2-terminal, hand-routed Kelvin taps |
| RS2 | Shunt, cable 2 | 2 | Bourns CSS2H-2512R-L500F, 0.5 mΩ | 2512, 2-terminal, hand-routed Kelvin taps |
| RS3 | Shunt, cable 3 (3-port SKU only) | 3 | Bourns CSS2H-2512R-L500F, 0.5 mΩ | 2512, 2-terminal, hand-routed Kelvin taps |
| J_IN1/J_OUT1 … J_IN3/J_OUT3 | PSU-side in / load-side out, per cable | 1–3 | Molex 45586-0005, Mini-Fit Jr, dual-row RA, 3rd-gen PCIe polarization | THT header |
| PCB copper | Bundled-shunt vertical transition, per cable | all | — | OQ-10 unresolved (same open item as EPS — per-cable 40–55A site) |

## Failure-mode rows

| Failure mode | Effect on monitored power path | Detection surface | In-path element | Severity | Fault-injection evidence ref |
|---|---|---|---|---|---|
| Shunt open (any cable) | That cable interrupted — direct pass-through failure, other cables unaffected (per-cable isolation) | ALERT/threshold (INA238 sudden zero-current) | RS1/RS2/RS3 | S3 | TBD — not yet run |
| Shunt short/solder-bridge | None on pass-through current; destroys Kelvin sensing on that cable | INA238 differential reads near-zero permanently; sensor-fault classification | RS1/RS2/RS3 | S1 | TBD — not yet run |
| Kelvin tap trace open | None on pass-through (off main current path by construction) | INA238 reads open/clamped input | RS1/2/3 Kelvin taps | S1 | TBD — not yet run |
| Bundled-shunt vertical transition failure | Localized resistance rise or open; potentially cable-interrupting at the extreme (60–75A transient per spec §6.4 table) | Rail-voltage sag, ALERT threshold, or bench thermal imaging | PCB copper (OQ-10 pending) | S2/S3 depending on extent | TBD — needs OQ-10 resolution + dedicated bench |
| J_IN/J_OUT connector pin fret (45586-0005 polarized header) | Localized derate under a single-pin fret | Rail-voltage sag under load; thermal imaging | J_IN{1,2,3}, J_OUT{1,2,3} | S2 | `bench-misplug-injection.md` (connector-stress leg, once run) |
| Cross-cable thermal coupling (dense 2-/3-cable layout) causing one cable's fault to elevate a neighbor's steady-state temperature | Neighbor cable's margin erodes without itself faulting — a compounding, not primary, effect | Thermal imaging during bench; no on-board NTC currently | PCB copper / shunt siting | S2 | TBD — not yet run |
| §6.13 transient-detection front-end fault (if populated) | None on pass-through — taps the shunt, not in series | Loss of transient-FREEZE capability only | INA181-class CSA, comparator | S1 | TBD — not yet run |
| RJ-45 link severed / mis-plug | None on the pass-through cables | DETECT-code mismatch, CAN bus-state, T1 link state (streaming family) | RJ-45 jack, pin-8 ESD diode | S1 (by design) | `bench-misplug-injection.md` |

## Fail-passive rows

See `fmea-template-common.md` §"Fail-passive rows" — all five triggers apply
verbatim per cable (2 or 3 independent instances depending on SKU); none
currently have dedicated fault-injection evidence (all `TBD`).

## Open findings

- OQ-10 (bundled-shunt vertical) unresolved — same open item as EPS, shared
  root cause (both families use the same per-cable shunt-site geometry class).
- Streaming family (100BASE-T1 per REQ-MOD-COMMON-003) — carries the full
  survey-11 T1 protection network on pins 4/5; not yet an in-path row pending
  BOM landing.
- The 3-port SKU's third cable (RS3/J_IN3/J_OUT3) has no dedicated cross-cable
  thermal or mechanical isolation analysis yet — flagged as the compounding
  row above, needs its own bench pass once boards exist.
- Shunt MPN not yet written into `modules/pcie-8pin-*/bom/*.csv` (same
  OQ-11-sheet-ahead-of-BOM gap noted on the EPS worksheet).
