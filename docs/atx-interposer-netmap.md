# 24-pin ATX interposer — net map (J3 = PSU side (IN), J4 = motherboard side (OUT))
# Connector symbol: cec:CEC_ATX_24 (24 pins). Two instances: J3, J4.

## 1. SENSED RAILS — detour through shunt (each rail's pins bundled both sides)
  +12V:
     HI net 'RAIL12V_HI'  = J3.10 + J3.11 + RS1.1
     LO net 'RAIL12V_LO'  = J4.10 + J4.11 + RS1.2   (LO also -> INA Vin-/Vbus, already wired)
  +5V:
     HI net 'RAIL5V_HI'  = J3.4 + J3.6 + J3.21 + J3.22 + J3.23 + RS2.1
     LO net 'RAIL5V_LO'  = J4.4 + J4.6 + J4.21 + J4.22 + J4.23 + RS2.2   (LO also -> INA Vin-/Vbus, already wired)
  +3.3V:
     HI net 'RAIL3V3_HI'  = J3.1 + J3.2 + J3.12 + J3.13 + RS3.1
     LO net 'RAIL3V3_LO'  = J4.1 + J4.2 + J4.12 + J4.13 + RS3.2   (LO also -> INA Vin-/Vbus, already wired)
  +5VSB:
     HI net 'RAIL5VSB_HI'  = J3.9 + RS4.1
     LO net 'RAIL5VSB_LO'  = J4.9 + RS4.2   (LO also -> INA Vin-/Vbus, already wired)

## 2. GND — single shared net (not shunted), all pins both connectors + module GND
  GND = J3.3 + J3.5 + J3.7 + J3.15 + J3.17 + J3.18 + J3.19 + J3.24
      + J4.3 + J4.5 + J4.7 + J4.15 + J4.17 + J4.18 + J4.19 + J4.24
      + module GND (already the board GND net)

## 3. PASS-THROUGH (J3.n wired straight to J4.n, not sensed)
  -12V    : J3.14  <-> J4.14
  PWR_OK  : J3.8  <-> J4.8     (also MONITORED — see section 4)
  PS_ON#  : J3.16  <-> J4.16   (also MONITORED — see section 4)
  NC      : J3.20  <-> J4.20  (NC: may leave both unconnected instead of strapping)

## 4. LOGIC-SIGNAL MONITORING — PWR_OK and PS_ON# (high-impedance taps)  [AS-BUILT]
  These are logic signals, NOT power rails: do NOT break/shunt them. They stay as
  the straight pass-throughs in section 3; we only TAP them to read state on the
  ESP32. The motherboard still drives/sees them unchanged. Both are PSU-side ~+5V
  logic, above the ESP32-S3 3.3V GPIO max, so each goes through a divider.

  PWR_OK  -> 10k/10k divider (R5/R6) -> IO4.
    PWR_OK is a push-pull "power good" output (low source impedance), so a 10k/10k
    tap doesn't disturb it. ~2.5V high / 0V low.
    Nets: 'PWR_OK' (J3.8<->J4.8) -> R5.1 ; 'PWR_OK_SENSE' = R5.2 + R6.1 + U1.8(IO4) ;
          GND += R6.2

  PS_ON# -> 100k/100k divider (R7/R8) + 100nF (C8) to GND -> IO5 (ADC1).
    PS_ON# idle (OFF) voltage is set by the PSU's internal pull-up to +5VSB, whose
    value is PSU-dependent and can be weak. Use a HIGH-impedance 100k/100k divider
    (200k to GND) so we don't load that pull-up and shift the OFF level / on-off
    threshold. Output source impedance is then ~50k — too high for the ESP32 SAR
    ADC's sample-and-hold, so C8 (100nF) at the sense node gives it a low-impedance
    charge reservoir. Valid because PS_ON# is a slow state line: 50k*100nF ~ 5ms
    (~32Hz), so allow ~25ms settle after a PS_ON# edge before trusting the read.
    Read on IO5 = ADC1 channel (ADC1, not ADC2 — ADC2 conflicts with WiFi).
    Nets: 'PS_ON#' (J3.16<->J4.16) -> R7.1 ;
          'PS_ON_SENSE' = R7.2 + R8.1 + C8.<sense> + U1.9(IO5) ;
          GND += R8.2 + C8.<gnd>     <-- C8 ground leg MUST tie to GND

  These taps are independent of the rail sensing; they add no load to the shunts
  and need no INA228.

## 5. MODULE SELF-SUPPLY tap (decision: PSU-side / HI, before RS4)
  The module's own +5VSB (LP5907 U3.1 input, C1.1, and J2.1 power-out to Hub)
  taps the +5VSB HI node so module/Hub self-draw is NOT counted in the 5VSB reading:
     add U3.1, C1.1, C4.1, U2.3, J2.1  to net 'RAIL5VSB_HI'
  (Today those sit on a plain '+5VSB' net; merge that net into RAIL5VSB_HI,
   i.e. the PSU-side of RS4 becomes the board's +5VSB source node.)
  J4.9 (+5VSB to motherboard) stays on RAIL5VSB_LO (after the shunt).

## 6. INA ALERT MONITORING — §6.10 ring-buffer-freeze trigger (per-rail)
  Each INA228 ALERT (open-drain, active-low) routes to its own ESP32 GPIO so
  firmware can use it as the threshold detector / buffer-freeze trigger (§6.10).
  ALERT is no-connect on all four INAs today — remove those NC flags to wire it.

  Per-rail assignment (4 spare GPIOs, all verified free; not strapping/USB/flash):
     U10 (12V)  ALERT (pin 3) -> ESP32 IO10   net 'ALERT_12V'
     U11 (5V)   ALERT (pin 3) -> ESP32 IO11   net 'ALERT_5V'
     U12 (3V3)  ALERT (pin 3) -> ESP32 IO12   net 'ALERT_3V3'
     U13 (5VSB) ALERT (pin 3) -> ESP32 IO13   net 'ALERT_5VSB'

  GUI steps (do alongside the Vin+/Vin- polarity rewire):
   - Delete the no-connect (X) on each INA ALERT pin (U10-U13 pin 3) AND on the
     four target GPIOs (IO10-IO13).
   - Drop a matching label on each ALERT stub and its GPIO (ALERT_12V, etc.).

  Pull-up: ALERT is open-drain, so it needs a pull-up to +3V3. Simplest is the
  ESP32 internal pull-ups (firmware-enabled) — fine for short on-board traces,
  no parts. For a hardware-defined pull-up add 4x 10k to +3V3 at the GPIOs. (None
  on the board today.)

## PRE-PCB-CAPTURE CHECKLIST (24-pin)
  [x] Shunt values restored to §6.4: RS1/RS2/RS3 = 2mΩ, RS4 = 25mΩ.
  [x] INA Vin+/Vin- polarity: Vin+ on _HI (PSU/J3) on all four INAs (verified).
  [x] INA ALERT: per-rail U10-U13 -> IO10-IO13 (verified).
  [x] PS_ON# divider raised to 100k/100k + 100nF (C8) to GND, read on IO5/ADC1.
  [ ] C8 ground leg: C8.1 is currently FLOATING (no wire). Tie it to GND, else the
      100nF does nothing and the ADC sees the raw ~50k source impedance.
  [ ] Re-run ERC (will flag C8.1 and any other unconnected pins from the wiring pass).

## NOTE: pin 11 (+12V) and pin 13 (+3.3V) — confirm against your PSU/mobo
  ATX 2.x sometimes labels pin 11/12 differently across revisions; the KiCad
  ATX-24 standard assignment is used here. Verify pin 11=+12V, 12/13=+3.3V on
  your target before fab.
