# 24-pin ATX interposer — net map (J_IN = PSU side, J_OUT = motherboard side)
# Connector symbol: cec:CEC_ATX_24 (24 pins). Two instances: J_IN, J_OUT.

## 1. SENSED RAILS — detour through shunt (each rail's pins bundled both sides)
  +12V:
     HI net 'SENSE12V_HI'  = J_IN.10 + J_IN.11 + RS1.1
     LO net 'SENSE12V_LO'  = J_OUT.10 + J_OUT.11 + RS1.2   (LO also -> INA Vin-/Vbus, already wired)
  +5V:
     HI net 'SENSE5V_HI'  = J_IN.4 + J_IN.6 + J_IN.21 + J_IN.22 + J_IN.23 + RS2.1
     LO net 'SENSE5V_LO'  = J_OUT.4 + J_OUT.6 + J_OUT.21 + J_OUT.22 + J_OUT.23 + RS2.2   (LO also -> INA Vin-/Vbus, already wired)
  +3.3V:
     HI net 'SENSE3V3_HI'  = J_IN.1 + J_IN.2 + J_IN.12 + J_IN.13 + RS3.1
     LO net 'SENSE3V3_LO'  = J_OUT.1 + J_OUT.2 + J_OUT.12 + J_OUT.13 + RS3.2   (LO also -> INA Vin-/Vbus, already wired)
  +5VSB:
     HI net 'SENSE5VSB_HI'  = J_IN.9 + RS4.1
     LO net 'SENSE5VSB_LO'  = J_OUT.9 + RS4.2   (LO also -> INA Vin-/Vbus, already wired)

## 2. GND — single shared net (not shunted), all pins both connectors + module GND
  GND = J_IN.3 + J_IN.5 + J_IN.7 + J_IN.15 + J_IN.17 + J_IN.18 + J_IN.19 + J_IN.24
      + J_OUT.3 + J_OUT.5 + J_OUT.7 + J_OUT.15 + J_OUT.17 + J_OUT.18 + J_OUT.19 + J_OUT.24
      + module GND (already the board GND net)

## 3. PASS-THROUGH (J_IN.n wired straight to J_OUT.n, not sensed)
  -12V    : J_IN.14  <-> J_OUT.14
  PWR_OK  : J_IN.8  <-> J_OUT.8
  PS_ON#  : J_IN.16  <-> J_OUT.16
  NC      : J_IN.20  <-> J_OUT.20  (NC: may leave both unconnected instead of strapping)

## 4. MODULE SELF-SUPPLY tap (decision: PSU-side / HI, before RS4)
  The module's own +5VSB (LP5907 U3.1 input, C1.1, and J2.1 power-out to Hub)
  taps the +5VSB HI node so module/Hub self-draw is NOT counted in the 5VSB reading:
     add U3.1, C1.1, C4.1, U2.3, J2.1  to net 'SENSE5VSB_HI'
  (Today those sit on a plain '+5VSB' net; merge that net into SENSE5VSB_HI,
   i.e. the PSU-side of RS4 becomes the board's +5VSB source node.)
  J_OUT.9 (+5VSB to motherboard) stays on SENSE5VSB_LO (after the shunt).

## NOTE: pin 11 (+12V) and pin 13 (+3.3V) — confirm against your PSU/mobo
  ATX 2.x sometimes labels pin 11/12 differently across revisions; the KiCad
  ATX-24 standard assignment is used here. Verify pin 11=+12V, 12/13=+3.3V on
  your target before fab.
