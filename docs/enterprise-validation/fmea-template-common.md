# FMEA template — common worksheet (per-family artifact: `fmea-template-{24pin,eps,pcie,12vhpwr}`)

Verification artifact for **REQ-MOD-COMMON-030** (fail-passive interposer
guarantee), **REQ-MOD-COMMON-031** (per-family FMEA/FMEDA with fault-injection
evidence), **REQ-MOD-COMMON-032** (in-path connector/copper thermal margins), and
**REQ-HUB-COMMON-081**. This is the shared worksheet structure; the four
instantiated files (`fmea-template-24pin.md`, `-eps.md`, `-pcie.md`,
`-12vhpwr.md`) pre-seed it with each family's real in-path elements.

**Depth ruling (trajectory scope, decision point "FMEA depth")**: qualitative FMEA
now, **quantitative FMEDA (failure rates, diagnostic coverage %) deferred until
OQ-11 (shunt part lock) and the survey-11 protection-network parts land in a
BOM** — avoids rework analyzing TBD parts. As of this writing OQ-11 has a
selection sheet (`docs/enterprise-requirements/ratification/
oq-11-shunt-selection-2026-07-02.md`) with exact MPNs per family but the formal
close still rides the pending v1.2.0 spec-text pass — treat every shunt MPN
below as ratified-pending-that-edit, not yet FMEDA-ready.

## Worksheet columns

| Column | Meaning |
|---|---|
| **Failure mode** | The specific way an in-path element fails (open, short, drift, mechanical, thermal). Named per element, not generically ("MCU dead" is a system-level trigger, not a row — see §"System-level triggers" below). |
| **Effect on monitored power path** | What happens to the pass-through 12V/5V/3V3/5VSB delivery the module sits in series with — NOT what happens to sensing accuracy. A row whose only effect is "sensing goes blind" is a detection-surface finding, not a fail-passive violation. |
| **Detection surface** | How the platform observes this failure: ALERT/threshold (§6.10 acquisition model), DETECT-code mismatch, CAN bus-state (error-passive/bus-off), thermal (NTC where present), or "none identified" (an honest gap, not a blank). |
| **In-path element** | The specific part/reference designator/PCB feature in the pass-through path (shunt, connector, copper vertical) — see the per-family pre-seed. Sensing-only components (INA228/238/240, ESP32, CAN transceiver) are NOT in-path; their failure modes belong in the fail-passive rows below, not here. |
| **Severity** | S1 negligible (sensing/telemetry degraded only, pass-through power unaffected) / S2 moderate (pass-through derates but continues, e.g. added series resistance from a partial connector fault) / S3 major (pass-through power interrupted, degraded below spec, or destabilized — any S3 finding is a REQ-MOD-COMMON-030 violation and MUST be designed out, not accepted with a note). |
| **Fault-injection evidence ref** | Pointer to the actual injection test that produced evidence for this row: `bench-misplug-injection.md` run ID for connector/pin faults, a dedicated shunt/copper fault-injection bench run ID (open-shunt, shorted-shunt, thermal-cycling), or `TBD — not yet run` where evidence doesn't exist yet. A row with severity S3 and evidence `TBD` is the reason REQ-MOD-COMMON-031 gates GA. |

## Fail-passive rows (REQ-MOD-COMMON-030 — every family carries these verbatim)

REQ-MOD-COMMON-030's text names five specific single-fault triggers; every
family's instantiated FMEA restates these five as baseline rows, because they
are system-level (not tied to one in-path element) and are the actual claim
REQ-030 makes:

| Trigger | Required effect on pass-through power |
|---|---|
| MCU dead (crashed, browned out, unprogrammed) | None — pass-through is a passive/analog current path independent of MCU liveness (INA sense taps and any active limiter must not open the path on MCU loss). |
| Sensor shorted (INA228/238/240 input pin shorted to a rail) | None — sense taps are high-impedance off the pass-through conductor; a shorted sense input must not pull down or short the monitored rail itself. |
| Firmware crash / watchdog reset | None — same reasoning as MCU dead; a crash-loop must not toggle any element in series with the power path. |
| Link severed (RJ-45 cable unplugged or CAN/T1 down) | None — the module is a physical pass-through independent of its telemetry uplink; losing the Hub link must not affect the PSU-to-load power delivery. |
| 5VSB lost (module's own housekeeping power fails) | None — same class as MCU dead; the housekeeping rail is not in the high-current pass-through path by design (§2.7/§2.8), so its loss must not couple into it. |

## PCB-vertical / thermal margin rows (REQ-MOD-COMMON-032)

Every family with a bundled-shunt or per-pin vertical current transition
(via field, copper coin, or plated slot per OQ-10; layer-routing choice per
OQ-12) carries a row for the vertical itself, referencing the family's
declared production cooling model (12VHPWR precedent: TIM/case coupling stated,
still-air bound published as the conservative number, per CLAUDE.md action
item 4).

## Notes for every instantiated file

- In-path elements are pre-seeded from CLAUDE.md's per-board build state and
  the OQ-11 shunt selection sheet; MPNs shown are the sheet's selection, not yet
  a closed OQ-11 (see depth-ruling note above).
- **FMEDA upgrade** (failure rates + diagnostic coverage %) is explicitly
  deferred, per family, until (a) OQ-11 formally closes via the v1.2.0 spec
  edit and (b) `bench-misplug-injection.md` / a dedicated shunt fault-injection
  bench has produced real evidence to calibrate rates against — do not
  backfill FMEDA numbers from datasheet MTBF alone without bench corroboration.
