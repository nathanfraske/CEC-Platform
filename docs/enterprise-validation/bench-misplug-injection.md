# Bench spec: RJ-45 mis-plug injection rig (`bench-misplug-injection`)

Verification artifact for **REQ-HUB-COMMON-110** (Hub port fail-safe against a
live network cable mis-plug) and **REQ-MOD-COMMON-053** (mirror requirement,
module-side jack). Formalizes `docs/enterprise-requirements/research/phase2/
survey-11-misplug-failsafe.md` §h into a runnable procedure — the procedure
below is that section made concrete, not a redesign of it.

**Status**: spec only (`verification-map.json` status `planned`). Writing this
spec needs no hardware; **running** it is gated (§6).

## 1. Why this bench exists

The CEC pin table (`CLAUDE.md` §2.2/§2.3) is wired in literal T568B order, so a
standard patch cable maps CEC's DC pinout directly onto Ethernet/PoE pair
structure (survey-11 §Scope). A real Ethernet jack on the ENT-NET faceplate
makes a live-cable mis-plug foreseeable misuse, not deliberate abuse — the
consumer §2.4 "internal-only jack" ratification does not transfer. This bench
is the adversarial fixture the threat model and REQ-110/053 both presuppose.

## 2. Source list (survey-11 §h, verbatim scope)

1. Compliant 802.3af PSE (IEEE detection handshake).
2. Compliant 802.3at PSE.
3. Compliant 802.3bt Type 3/4 PSE, if available.
4. Passive 24 V injector (no handshake).
5. Passive 48 V injector (no handshake).
6. Passive ~56–57 V injector — bench supply, **no handshake**, the worst-case,
   always-on scenario REQ-HUB-COMMON-110 names explicitly.
7. Plain non-PoE 10/100/1000BASE-T switch port — baseline signaling-
   compatibility check.

**Both polarities** for every source: trivial for passive injectors (swap
leads / crossover fixture); for compliant PSEs, use test equipment allowing
polarity selection or accept the PSE's own convention and record which.

## 3. DUT matrix

| DUT | Rationale |
|---|---|
| 1x Hub Enterprise port, fully populated with the survey-11 §b protection network (SS110 + SMAJ58A on pin 1, series-R ahead of DETECT clamp, pin-7 bleed-R+TVS, T1 CMC+caps+TVS) | Hub-side exposure model: Hub sources +5VSB, so pin 1 needs the reverse-blocking diode (§a note 1). |
| 1x streaming-family module (EPS or PCIe — carries the 100BASE-T1 protection network per REQ-MOD-COMMON-003) | Module-side exposure: pin 1 is a module *input*, needing the active TPS26621-class OVP eFuse — a diode cannot protect it. |
| 1x 24-pin module (non-streaming, CAN-only pair-2 termination) | Simpler exposure — confirms the non-streaming family isn't over/under-protected (§h REQ-text-refinement note 2). |

Every other family inherits this procedure at GA per REQ-MOD-COMMON-050
lifecycle parity; this minimum DUT set matches survey-11 §h's own floor.

## 4. Protocol

Per source, per DUT, per polarity:

1. **Instantaneous exposure** — first seconds, watch for any visible/
   measurable fault.
2. **Sustained exposure — 60 minutes continuous.** Catches slow thermal
   failure a short pulse test misses ("left plugged in overnight," §h.2).
3. **Repeat the full cycle 5–10× on the same physical unit** (§h.5). **This is
   a GA gate, not a per-iteration bring-up requirement** — during firmware/
   board bring-up, one clean cycle per source/DUT/polarity is sufficient to
   proceed; the full 5–10× count is reserved for the GA release candidate,
   bounding the lab-time cost the trajectory scope doc flags (risk #5).
4. Run the plain non-PoE switch case (source 7) as baseline: no damage AND
   firmware correctly flags an unrecognized device rather than misreading
   switch signaling as a valid module class.

## 5. Instrumentation

- Current probes on pins 1, 3, 6, 4, 5, 7, 8 (every pin with a defined
  protection element, §b/§c).
- Thermal imaging on every protection component (SS110, SMAJ58A, DETECT
  series-R, pin-7 bleed-R, T1 CMC/caps/TVS, TPS26621 eFuse).
- Scope capture of the DETECT ADC node and the CAN bus, for alarm-detection
  response time.
- eFuse status pin (module side) logged continuously to confirm trip/
  auto-retry directly, not just inferred from current.

## 6. Pass criteria (must all hold — survey-11 §h)

- No visible or measurable component damage, before or after sustained
  exposure.
- Each protection element behaves within its envelope: diode holds off
  reverse current; eFuse trips + reports fault via status pin; TVS/clamp
  conducts only for genuine over-threshold excursions, not during the
  accepted 57 V steady state.
- Anomalous condition **detected, alarmed, and logged** within the bounded/
  debounced alarm window (REQ-HUB-COMMON-050), via DETECT-code mismatch,
  corroborated for CAN-pin stress by the bus-state monitor (REQ-HUB-COMMON-054).
- **Full function restored, unattended, after fault removal** — re-plug a real
  CEC module post-test and confirm DETECT-code read, CAN comms, and (streaming
  families) 100BASE-T1 link-up succeed with no manual intervention.
- **Containment**: a mis-plugged port SHALL NOT disturb other ports, the
  shared CAN bus, or Hub operation — verify via an adjacent unfaulted port's
  telemetry continuity through the fault window.
- **Repeat-cycle criterion**: 5–10× survival is the GA-gate pass condition
  (§4.3); explicitly NOT required at bring-up.

## 7. Execution gates (hardware needed)

A fabricated Hub port + one module per family with the survey-11 protection
network actually populated (not yet on any BOM). This bench also doubles as
fault-injection evidence input to `fmea-template-*.md` (REQ-MOD-COMMON-031
already requires fault-injection evidence for in-path power elements) — run as
one combined program, per survey-11 §h's closing note.
