# EMC pre-scan plan

Verification artifact for **REQ-HUB-COMMON-095**. `verification-map.json` artifact key:
`emc-prescan-plan`. **Status: plan only — gated on a populated PCB revision existing**;
no in-house rig has been assembled yet.

## 1. Posture: in-house triage first, paid lab as an escalation, not a default

Per the scope-validation decision lean, **every hardware revision** gets an in-house
near-field/spectrum triage before any paid lab time is booked. A full paid EN
55032/55035 pre-compliance run is reserved for (a) **pre-GA** of a given SKU, and (b)
**after any RF-relevant change** — specifically a new/changed 100BASE-T1 PHY population
(DP83TC814S-Q1 default per REQ-MOD-COMMON-003) or uplink magnetics (LAN9370 RGMII/T1
front end, REQ-HUB-COMMON-043). A revision with no RF-relevant change since its last
lab-verified pass does not automatically re-trigger a paid slot — see §3.

## 2. In-house triage rig

- **Near-field probe set** (H-field loop + E-field probes, small-loop class) + a
  bench/USB spectrum analyzer covering at minimum 150 kHz–1 GHz (30 MHz–1 GHz is the
  EN 55032 conducted/radiated floor; extend toward 6 GHz once the 100BASE-T1/LAN9370
  RGMII clock harmonics are characterized).
- Probe every board at: clock/oscillator sources (ESP32-P4 crystal, LAN9370 refclk),
  the T1 PHY's magnetics/line-side, switching regulators (buck converters on both Hub
  and modules), and any cable exit point (RJ-45, 12V-2x6, USB-C).
- Compare each sweep against the prior revision's captured baseline (not an absolute
  pass/fail line) — the in-house rig has no calibrated antenna/chamber, so its value is
  **regression detection and gross-offender triage**, not a compliance number.

## 3. Escalation criteria to a paid lab slot

Escalate to a booked EN 55032 (emissions, Class A/B per intended environment) and EN
55035 (immunity) lab slot when **any** of:

1. The SKU is entering **pre-GA** for its market (a lab-verified pass is a GA gate, not
   optional, per REQ-HUB-COMMON-095's per-revision requirement).
2. The revision changed a **T1 PHY population or its magnetics** vs. the last
   lab-verified revision.
3. The revision changed **uplink magnetics** (any new/changed transformer, choke, or
   connector on the Ethernet/T1 uplink path) vs. the last lab-verified revision.
4. In-house triage shows a near-field hotspot or spectral peak with no prior-revision
   baseline to compare against (new design, not incremental).

A revision that only changes firmware, non-RF passives, or mechanical/enclosure details
with no RF-path change stays in-house-triage-only.

## 4. ATR note — an avoided-cost record

The anti-tamper-radio (ATR) module family was ratified **passive receive-only**
(owner ruling 2026-07-02, 9th; R6/OQ-78) for the NET SKU, with the **active-emitter
variant deferred to customer-funded NRE**. This directly changes this plan's scope:

- A **passive-receive-only RF sensor is not an intentional radiator** — it has no FCC
  Part 15 Subpart C (or equivalent EU intentional-radiator) certification path to carry
  at all. The adopted design therefore needs **no new intentional-radiator EMC
  test/cert line item** in this plan.
- Record this as an explicit **avoided cost**: had the active-emitter (UWB pulse) ATR
  variant shipped fleet-wide instead of being deferred, it would have added its own
  Part-15C-class (or EU RED Article 3.2 radio) certification cycle on top of the
  EN 55032/55035 scope already covered here — a materially larger and separate
  compliance line, not a marginal add to this plan.
- If the active-emitter variant is later funded (customer-specific NRE), this plan's
  scope reopens to add that certification path; it is out of scope for the current
  NET-only, receive-only ATR design.
