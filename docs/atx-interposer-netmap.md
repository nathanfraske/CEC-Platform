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

## 4. LOGIC-SIGNAL MONITORING — PWR_OK and PS_ON# (74LVC1G17 buffers) [AS-BUILT]
  These are logic signals, NOT power rails: do NOT break/shunt them. They stay as
  the straight pass-throughs in section 3; we only TAP them to read state on the
  ESP32. The motherboard still drives/sees them unchanged. Both are PSU-side ~+5V
  logic, above the ESP32-S3 3.3V GPIO max.

  Both go through a 74LVC1G17 single-gate Schmitt buffer (U4 = PWR_OK, U5 = PS_ON#):
    - 5V-tolerant input: PWR_OK/PS_ON# drive pin A directly — no divider, no
      level-shift network.
    - High-Z input: no loading. For PS_ON# this is the key win — its OFF level is
      set by the PSU's (possibly weak) internal +5VSB pull-up and the buffer won't
      disturb it. (This replaced the earlier 100k/100k + 100nF + ADC scheme.)
    - Schmitt hysteresis: clean edges / noise immunity; output is rail-to-rail 3V3.
    - Each buffer: VCC=+3V3, GND, + 100nF decoupler (C9 on U4, C14 on U5).
    - Output Y -> a plain digital GPIO: PWR_OK -> U1 IO4, PS_ON# -> U1 IO5.
  Both reads are DIGITAL now, so no ADC channel is consumed (ADC1 fully free).

  Nets: 'PWR_OK' (J3.8<->J4.8) -> U4.A ; U4.Y -> IO4.
        'PS_ON#' (J3.16<->J4.16) -> U5.A ; U5.Y -> IO5.
  (The old R5/R6 PWR_OK divider and R7/R8 + C8 PS_ON# divider are removed.)

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
  [x] PWR_OK + PS_ON# both via 74LVC1G17 buffers (U4/U5) -> IO4/IO5, digital (sec 4).
  [x] Footprints assigned + vendored; connectors are right-angle (inline).
  [x] RS1-3 = Bourns CSS2H-2512K-2L00F (5W); RS4 = Vishay WSK2512 (5VSB).
  [ ] Create/verify the exact Bourns CSS2H-2512 land pattern (RS1-3 currently use a
      WSK2512 2512 4-term Kelvin stand-in footprint).
  [ ] Re-run ERC after the buffer rework (R7/R8/C8 removed, U5/C14 added).

## NOTE: pin 11 (+12V) and pin 13 (+3.3V) — confirm against your PSU/mobo
  ATX 2.x sometimes labels pin 11/12 differently across revisions; the KiCad
  ATX-24 standard assignment is used here. Verify pin 11=+12V, 12/13=+3.3V on
  your target before fab.
