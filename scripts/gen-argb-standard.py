#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  gen-argb-standard -- BORN-HIERARCHICAL generator for the CEC ARGB
#  Controller Standard (8-channel), spec Section 7. Owner directive
#  (2026-07-05): "let's design out the standard tier ARGB hub as well. This is
#  the one that should be able to be fully standalone... it should come with
#  everything needed to slot right in."
# ============================================================================
# NEW BOARD (nothing existed before this pass) -- built directly through
# scripts/cec_sch_compose.py (Leaf/Compose/build_leaf/build_thin_parent), the
# modules/ent-common "from birth" pattern (gen_p4_t1_block.py), NOT a
# flat-schematic-converter like gen-module-beta.py/gen-12vhpwr-beta.py (there
# is no pre-existing flat sheet to extract from). Rev BETA-1 + a DRAFT marker
# (new board, no alpha lineage, pre-fab -- the output-daughterboard precedent).
#
# PARTITION (8 literal leaf sheets, one functional block per sheet):
#   01-power-input   J1(SATA 15P) Q1(P-FET) F1(fuse) RT1(inrush NTC)
#                    R1-R3, C1-C2         spec Sec 7.2
#   02-sense         RS1(shunt) U4(INA180A2) C3    spec Sec 7.4
#   03-hub-link      J2(RJ45 FTP) DETECT chain FB1  spec Sec 2.1/2.3/2.4/7.5
#   04-can           U2(TJA1051T/3) FL1(CMC,DNP) H3a bypass   spec Sec 3.1/7.5
#   07-usb-flash     J3(USB-C) H3 ESD/EMC suite      spec Sec 6.14/7.5
#   05-mcu           U1(ESP32-S3-MINI-1) U3(LDO) + 3-way logic-power OR
#   06-led-outputs   U5(74AHCT244) + 8x(R,BAT54S,PESD,J_LED)   spec Sec 7.3
#   08-status        U6(SN74AHCT1G08) DL1(SK6812MINI), optional/populated
#
# Every net is either a genuine 2-leaf PAIR (a real drawn lane in the thin
# parent) or the ONE true N-way bus (+5V_LED, produced in 02-sense, consumed
# in BOTH 05-mcu and 06-led-outputs) via `global_nets` (project-wide
# `global_label`, the same mechanism hub-enterprise's sheet-05 CAN bus uses).
#
#   python3 scripts/gen-argb-standard.py [--force]
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cec_sch                # noqa: E402
import cec_sch_compose as C   # noqa: E402
import cec_sch_layout as L    # noqa: E402
import cec_sch_gates as G     # noqa: E402
import cec_sch_archetypes as arch  # noqa: E402

BOARD = "argb-standard"
BOARD_DIR = os.path.join(ROOT, "modules", BOARD)
PROJECT_NAME = "argb-standard-module"
ROOT_SCH = os.path.join(BOARD_DIR, f"{PROJECT_NAME}.kicad_sch")
REV = "BETA-1"

LIBS = {
    "cec":                 open(f"{ROOT}/lib/cec.kicad_sym").read(),
    "cec-vendor":          open(f"{ROOT}/lib/vendor/cec-vendor.kicad_sym").read(),
    "power":               open(f"{ROOT}/lib/vendor/cec-power.kicad_sym").read(),
    "cec-Connector_Generic": open(f"{ROOT}/lib/vendor/Connector_Generic.kicad_sym").read(),
}
POWER_PORTS = {"GND": "GND", "+3V3": "+3V3"}

# Fixed identity uuids (stable across regenerations).
ROOT_UUID = "8a1e9c7d-2b4f-4a6e-9d3c-5f7e1b8a9c01"
LEAF_SYM_UUIDS = {
    "01-power-input": "8a1e9c7d-2b4f-4a6e-9d3c-5f7e1b8a9c11",
    "02-sense":       "8a1e9c7d-2b4f-4a6e-9d3c-5f7e1b8a9c12",
    "03-hub-link":    "8a1e9c7d-2b4f-4a6e-9d3c-5f7e1b8a9c13",
    "04-can":         "8a1e9c7d-2b4f-4a6e-9d3c-5f7e1b8a9c14",
    "07-usb-flash":   "8a1e9c7d-2b4f-4a6e-9d3c-5f7e1b8a9c17",
    "05-mcu":         "8a1e9c7d-2b4f-4a6e-9d3c-5f7e1b8a9c15",
    "06-led-outputs": "8a1e9c7d-2b4f-4a6e-9d3c-5f7e1b8a9c16",
    "08-status":      "8a1e9c7d-2b4f-4a6e-9d3c-5f7e1b8a9c18",
}
LEAF_OWN_UUIDS = {
    "01-power-input": "9b2f0d8e-3c5a-4b7f-8e4d-6a8f2c9b0d21",
    "02-sense":       "9b2f0d8e-3c5a-4b7f-8e4d-6a8f2c9b0d22",
    "03-hub-link":    "9b2f0d8e-3c5a-4b7f-8e4d-6a8f2c9b0d23",
    "04-can":         "9b2f0d8e-3c5a-4b7f-8e4d-6a8f2c9b0d24",
    "07-usb-flash":   "9b2f0d8e-3c5a-4b7f-8e4d-6a8f2c9b0d27",
    "05-mcu":         "9b2f0d8e-3c5a-4b7f-8e4d-6a8f2c9b0d25",
    "06-led-outputs": "9b2f0d8e-3c5a-4b7f-8e4d-6a8f2c9b0d26",
    "08-status":      "9b2f0d8e-3c5a-4b7f-8e4d-6a8f2c9b0d28",
}

LEAF_META = {
    "01-power-input": ("01-power-input.kicad_sch", "01-power-input",
                       "SATA 15P IN -> P-FET reverse-polarity -> PPTC fuse -> "
                       "NTC inrush -> +5V_LED_IN; SATA-feed rail-voltage divider"),
    "02-sense":       ("02-sense.kicad_sch", "02-sense",
                       "Total-rail shunt + INA180A2 (50V/V) current sense -> +5V_LED"),
    "03-hub-link":    ("03-hub-link.kicad_sch", "03-hub-link",
                       "RJ-45 FTP + DETECT (2.2k CAN-only code) + 5VSB entry bead"),
    "04-can":         ("04-can.kicad_sch", "04-can",
                       "TJA1051T/3 + CAN CMC position (FL1, DNP) with the "
                       "H3a-PATTERN 0R bypasses R6/R7"),
    "07-usb-flash":   ("07-usb-flash.kicad_sch", "07-usb-flash",
                       "USB-C flash/debug + H3 standalone-mode USB ESD/EMC suite"),
    "05-mcu":         ("05-mcu.kicad_sch", "05-mcu",
                       "ESP32-S3-MINI-1 + BOOT/RESET + 3-way logic-power OR + LP5907 3V3 LDO"),
    "06-led-outputs": ("06-led-outputs.kicad_sch", "06-led-outputs",
                       "74AHCT244 octal level-shift + 8x (series R, BAT54S clamp, "
                       "PESD TVS, ARGB header)"),
    "08-status":      ("08-status.kicad_sch", "08-status",
                       "SK6812MINI status pixel (platform LED language), level-shifted"),
}
LEAF_ORDER = ["01-power-input", "02-sense", "03-hub-link", "04-can",
              "07-usb-flash", "05-mcu", "06-led-outputs", "08-status"]

# Pure geometric total order for the thin-parent's left/right box-side choice
# (see gen-12vhpwr-beta.py's identical RANK convention -- NOT a signal-flow
# direction, just "smaller rank sits physically left / exits its own right
# edge; larger rank sits physically right / receives on its own left edge").
RANK = {"01-power-input": 1, "02-sense": 2, "03-hub-link": 3, "04-can": 4,
        "07-usb-flash": 5, "05-mcu": 6, "06-led-outputs": 7, "08-status": 8}

Leaf = C.Leaf
LEAVES = {lid: Leaf(lid, *LEAF_META[lid][:2], LEAF_META[lid][2]) for lid in LEAF_ORDER}


def ap(lf, ref, lib, name, value, fp, props=None):
    """add_part with a dummy position -- the compose pass places everything."""
    lf.add_part(ref, lib, name, value, 0, 0, fp, props)


# ===========================================================================
# 01 -- power-input: SATA 15P -> P-FET -> PPTC fuse -> NTC inrush -> +5V_LED_IN
#       + the SATA-feed rail-voltage divider. Spec Sec 7.2 (LOCKED approach;
#       part VALUES are a working basis, flagged in README.md).
# ===========================================================================
L01 = LEAVES["01-power-input"]
ap(L01, "J1", "cec-Connector_Generic", "Conn_01x15", "SATA_PWR_15P",
   "",  # CONSIGNED: no credible LCSC SATA-15P male RA part found (see README)
   {"Manufacturer": "(consigned)", "MPN": "SATA power 15P male, right-angle (TBD)",
    "Description": "SATA power connector, 15-pin, board-mount male, right-angle. "
                   "No LCSC line exists for this shape (verified); source directly "
                   "from a connector house (e.g. KLS Connector KLS1-SATA family) "
                   "at BOM lock, matching the Mini-Fit Jr consigned-part precedent."})
ap(L01, "Q1", "cec-vendor", "AO4407A", "AO4407A",
   "cec-Package_SO:SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL",
   {"Manufacturer": "Alpha & Omega Semiconductor", "MPN": "AO4407A", "LCSC": "C16072",
    "Description": "P-channel MOSFold, logic-level Vgs(th) -1.7 to -3V, "
                   "ID -12A (25C), reverse-polarity series pass element"})
ap(L01, "F1", "cec-vendor", "2920L700_12MR", "2920L700/12MR",
   "cec-Fuse_SMD:F2920",
   {"Manufacturer": "Littelfuse", "MPN": "2920L700/12MR", "LCSC": "C207092",
    "Description": "Resettable PPTC fuse, 7A hold / 14A trip / 12V max"})
ap(L01, "RT1", "cec-vendor", "MF72-5D-20", "MF72-5D-20",
   "cec-Thermistor_THT:RES-TH_L22.0-W7.0-P10.00-D1.0-S2.00",
   {"Manufacturer": "Nanjing Shiheng Electronics", "MPN": "MF72-5D-20", "LCSC": "C122780",
    "Description": "Power NTC inrush-current limiter, 5 ohm cold / 7A rated "
                   "(controlled inrush element -- spec Sec 7.2; OOS at LCSC as of "
                   "2026-07-05, flagged, matches this repo's own precedent for a "
                   "real-but-thin-stock part, cf. the ESP32-S3-MINI-1 pick below)"})
ap(L01, "R1", "cec-vendor", "R_Small", "10k", "cec-Resistor_SMD:R_0402_1005Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF1002TCE", "LCSC": "C25744"})
ap(L01, "R2", "cec-vendor", "R_Small", "47k", "cec-Resistor_SMD:R_0402_1005Metric",
   # measured bug, fixed: C25900 (an earlier value here) is NOT 0402WGF4702TCE
   # -- verified against the live LCSC listing it is actually 0402WGF4701TCE
   # (4.7k, one decade off -- would have corrupted the ISENSE_TOTAL rail-
   # divider ratio). C25792 is the correct listing for the intended 47k
   # 0402WGF4702TCE (cross-checked against another board's own sourced BOM).
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF4702TCE", "LCSC": "C25792"})
ap(L01, "R3", "cec-vendor", "R_Small", "10k", "cec-Resistor_SMD:R_0402_1005Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF1002TCE", "LCSC": "C25744"})
ap(L01, "C1", "cec-vendor", "C_Small", "100u", "cec-Capacitor_SMD:C_1210_3225Metric",
   # measured bug, fixed: C96446 (an earlier value here) is NOT
   # CL32A107MQVNNNE -- verified against the live LCSC listing it is
   # actually CL10A106MA8NRNC (10uF 0603 -- wrong value AND wrong
   # footprint/package entirely). C49066 is the correct listing (confirmed
   # against the live LCSC page: "CAP CER 100uF 6.3V X5R 1210").
   {"Manufacturer": "Samsung", "MPN": "CL32A107MQVNNNE", "LCSC": "C49066",
    "Description": "+5V_LED bulk cap, charged (slew-limited) through RT1"})
ap(L01, "C2", "cec-vendor", "C_Small", "1n", "cec-Capacitor_SMD:C_0402_1005Metric",
   {"Manufacturer": "Murata", "MPN": "GRM1555C1H102JA01D", "LCSC": "C76947",
    "Description": "Rail-divider ADC filter cap (matches the 12VHPWR VRAIL_DIV precedent)"})

L01.net("SATA_5V_RAW", ("J1", "7"), ("J1", "8"), ("J1", "9"), ("Q1", "1"), ("Q1", "2"), ("Q1", "3"))
L01.net("GND", ("J1", "4"), ("J1", "5"), ("J1", "6"), ("J1", "10"), ("J1", "11"), ("J1", "12"),
        ("R1", "1"), ("C1", "2"), ("R3", "2"), ("C2", "2"))
L01.net("5V_POST_FET", ("Q1", "5"), ("Q1", "6"), ("Q1", "7"), ("Q1", "8"), ("F1", "1"))
L01.net("5V_POST_FUSE", ("F1", "2"), ("RT1", "1"))
L01.net("+5V_LED_IN", ("RT1", "2"), ("C1", "1"), ("R2", "1"))
# R1 pin roles are SWAPPED vs the naive pin1=GATE_Q1/pin2=GND assignment
# (measured bug, fixed): R1 sits ABOVE the gate at rot0, and R_Small's own
# geometry puts pin1 FARTHER from the gate (u_y=30) than pin2 (u_y=34,
# closer to the gate at u_y=44) -- a straight vertical wire from the gate
# down to pin1 would necessarily pass THROUGH pin2's exact point first
# (30 < 34 < 44 on the same X), accidentally shorting the gate straight to
# GND at that pass-through point. Swapping so the NEARER pin (2) is
# GATE_Q1 and the FARTHER pin (1) is GND means the gate wire simply stops
# at its own pin, never touching the other.
L01.net("GATE_Q1", ("Q1", "4"), ("R1", "2"))
L01.net("VRAIL_5V_DIV", ("R2", "2"), ("R3", "1"), ("C2", "1"))
L01.hier_exports = {
    "+5V_LED_IN":   ("output", ("RT1", "2")),
    "VRAIL_5V_DIV": ("output", ("R2", "2")),
}
L01.powerflag_nets = ["GND"]
# J1 pins 1-3 (+3.3V) and 13-15 (+12V) are DROPPED by the fat-cable design
# (spec Sec 7.2 -- "dropping the 12V and 3.3V wires"); left with no net at
# all so the generic pass emits their no_connect flags, matching how every
# other module leaves an unused RJ-45/connector pin (e.g. Standard-tier
# STREAM_P/N) untouched rather than force-wiring a spare pin.


# ===========================================================================
# 02 -- sense: total-rail shunt (RS1, 5mOhm) + INA180A2 (50V/V) -> +5V_LED
#       (the MEASURED, post-shunt rail every downstream block uses). Spec
#       Sec 7.4 (LOCKED direction: shunt + INA180A2; VALUE is a working
#       choice, math shown in README.md).
# ===========================================================================
L02 = LEAVES["02-sense"]
ap(L02, "RS1", "cec-vendor", "CEC_SHUNT_2T", "5mOhm",
   "cec-Resistor_SMD:R_2512_6332Metric",
   {"Manufacturer": "Milliohm", "MPN": "HoYLR2512-2W-5mR-1%", "LCSC": "C5375417",
    "Description": "Total-rail current shunt, 5mOhm/2W/1% -- see README.md Sec 2 "
                   "for the headroom math (working-choice value)"})
ap(L02, "U4", "cec-vendor", "INA180A2IDBVR", "INA180A2",
   "cec-Package_TO_SOT_SMD:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BL",
   {"Manufacturer": "Texas Instruments", "MPN": "INA180A2IDBVR", "LCSC": "C192764",
    "Description": "Current-sense amplifier, gain=50V/V (A2), spec Sec 7.4 LOCKED part"})
ap(L02, "C3", "cec-vendor", "C_Small", "100n", "cec-Capacitor_SMD:C_0402_1005Metric",
   {"Manufacturer": "Samsung", "MPN": "CL05B104KO5NNNC", "LCSC": "C1525"})

L02.net("+5V_LED_IN", ("RS1", "1"), ("U4", "3"))
L02.net("+5V_LED", ("RS1", "2"), ("U4", "4"), ("U4", "5"), ("C3", "1"))
L02.net("ISENSE_TOTAL", ("U4", "1"))
L02.net("GND", ("U4", "2"), ("C3", "2"))
L02.hier_exports = {
    "+5V_LED_IN":    ("input", ("RS1", "1")),
    "ISENSE_TOTAL":  ("output", ("U4", "1")),
}
L02.powerflag_nets = []
# NOTE: IN_HI/IN_LO reuse the "+5V_LED_IN"/"+5V_LED" connection points (RS1's
# own pads) rather than separate nets -- RS1.1 carries BOTH the +5V_LED_IN
# leaf-boundary net AND the INA180 Kelvin force/sense tap, same as every
# other CEC shunt (EPS/PCIe/12VHPWR): the tap is drawn off the shunt's own
# terminal copper at layout (Sec 6.8), a schematic-level shared node is
# correct and matches CEC_SHUNT_2T's own symbol description ("tap each INA
# sense lead off the terminal copper in LAYOUT").


# ===========================================================================
# 03 -- hub-link: RJ-45 FTP + DETECT (2.2k CAN-only code, module convention)
#       + 5VSB entry bead (H3a ferrite posture (b)). Spec Sec 2.1/2.3/2.4/7.5.
# ===========================================================================
L03 = LEAVES["03-hub-link"]
ap(L03, "J2", "cec", "CEC_RJ45_8P8C_FTP", "TO-HUB",
   "cec:RJ45_FTP_Shielded_Horizontal",
   {"Manufacturer": "Kinghelm", "MPN": "KH-RJ45-58-8P8C", "LCSC": "C2683360"})
ap(L03, "R4", "cec-vendor", "R_Small", "2k2", "cec-Resistor_SMD:R_0402_1005Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF2201TCE", "LCSC": "C25879",
    "Description": "DETECT code resistor: CAN-only link class (spec Sec 2.3)"})
ap(L03, "R5", "cec-vendor", "R_Small", "100k", "cec-Resistor_SMD:R_0402_1005Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF1003TCE", "LCSC": "C25741",
    "Description": "DETECT poke-and-ack high-Z tap (spec Sec 2.3)"})
ap(L03, "D1", "cec-vendor", "D_Schottky", "PESD5V0S1BA", "cec-Diode_SMD:D_SOD-323",
   {"Manufacturer": "Nexperia", "MPN": "PESD5V0S1BA", "LCSC": "C5261083",
    "Description": "DETECT pin-8 hot-plug ESD diode (spec Sec 2.4 LOCKED)"})
ap(L03, "FB1", "cec-vendor", "FerriteBead_Small", "0R", "cec-Capacitor_SMD:C_0805_2012Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0805W8F0000T5E", "LCSC": "C17477",
    "Description": "5VSB entry bead position, 0R-provisioned (H3a ferrite "
                   "posture (b) -- real bead swaps in only on EMC evidence)"})

L03.net("VCC_RJ45_RAW", ("J2", "1"), ("FB1", "1"))
L03.net("+5VSB_RJ", ("FB1", "2"))
L03.net("GND", ("J2", "2"), ("J2", "SH1"), ("J2", "SH2"), ("D1", "2"), ("R4", "2"))
L03.net("CAN_H_RJ", ("J2", "3"))
L03.net("CAN_L_RJ", ("J2", "6"))
L03.net("DETECT", ("J2", "8"), ("D1", "1"), ("R4", "1"), ("R5", "1"))
L03.net("DETECT_SENSE", ("R5", "2"))
# J2 pins 4/5 (STREAM_P/N) and 7 (reserved spare) are unused at Standard tier
# -- left with no net, generic pass emits their no_connect (spec Sec 2.2:
# "Standard tier leaves pair 2 unused, terminated at the module side").
L03.hier_exports = {
    "CAN_H_RJ":      ("output", ("J2", "3")),
    "CAN_L_RJ":      ("output", ("J2", "6")),
    "DETECT_SENSE":  ("output", ("R5", "2")),
}
# +5VSB_RJ is a GLOBAL bus (produced here, consumed in BOTH 04-can and
# 05-mcu -- a genuine 3-leaf net, not a 2-leaf pair), so it carries no
# sheet-pin/hier_exports entry at all; see build()'s global_nets wiring.
# GND itself needs NO powerflag_nets entry here (or on any other leaf
# besides 01-power-input): GND is a project-wide POWER_PORTS net that
# merges hierarchy-wide exactly like a global label, so ONE PWR_FLAG
# anywhere in the whole design satisfies ERC for every GND pin on every
# sheet (ent-common's own precedent: a single L01 entry covers all six of
# its leaves). Measured bug, fixed: an earlier version put a SEPARATE GND
# PWR_FLAG on 01-power-input, 03-hub-link, AND 07-usb-flash -- three
# independent "power output" assertions all driving the identical merged
# net, which ERC correctly flagged as a pin-to-pin "Power output and Power
# output are connected" ERROR between each pair. 01-power-input's single
# flag is retained as the one canonical anchor.
L03.powerflag_nets = []


# ===========================================================================
# 04 -- can: TJA1051T/3 (pins 3/6, classical 500k, no module termination) +
#       CAN CMC DNP position with the H3a-PATTERN 0R bypasses. Spec Sec 3.1/7.5.
# ===========================================================================
L04 = LEAVES["04-can"]
ap(L04, "U2", "cec-vendor", "TJA1051T-3", "TJA1051T/3",
   "cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
   {"Manufacturer": "NXP", "MPN": "TJA1051T/3", "LCSC": "C38695"})
ap(L04, "C4", "cec-vendor", "C_Small", "100n", "cec-Capacitor_SMD:C_0402_1005Metric",
   {"Manufacturer": "Samsung", "MPN": "CL05B104KO5NNNC", "LCSC": "C1525"})
ap(L04, "C5", "cec-vendor", "C_Small", "100n", "cec-Capacitor_SMD:C_0402_1005Metric",
   {"Manufacturer": "Samsung", "MPN": "CL05B104KO5NNNC", "LCSC": "C1525"})
ap(L04, "FL1", "cec-vendor", "CEC_CMC_4T", "CAN CMC position (ACT45B-510-2P-TL003), DNP",
   "cec-Common_Mode_Choke:CMC_SMD4P_L4.5xW3.2mm",
   {"Manufacturer": "TDK", "MPN": "ACT45B-510-2P-TL003", "LCSC": "C76584",
    "Description": "EMC insurance position, DNP-provisioned (OQ-83: platform "
                   "CMC part+footprint not yet converged; matches EPS/24-pin's "
                   "choice over 12VHPWR's ACT1210L)"})
ap(L04, "R6", "cec-vendor", "R_Small", "0R", "cec-Resistor_SMD:R_0402_1005Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF0000TCE", "LCSC": "C17168",
    "Description": "H3a-PATTERN populated bypass (FL1 CAN_H winding)"})
ap(L04, "R7", "cec-vendor", "R_Small", "0R", "cec-Resistor_SMD:R_0402_1005Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF0000TCE", "LCSC": "C17168",
    "Description": "H3a-PATTERN populated bypass (FL1 CAN_L winding)"})

L04.net("CAN_H_RJ", ("FL1", "1"), ("R6", "1"))
L04.net("CAN_H", ("FL1", "3"), ("R6", "2"), ("U2", "7"))
L04.net("CAN_L_RJ", ("FL1", "2"), ("R7", "1"))
L04.net("CAN_L", ("FL1", "4"), ("R7", "2"), ("U2", "6"))
L04.net("CAN_TX", ("U2", "1"))
L04.net("CAN_RX", ("U2", "4"))
L04.net("+5VSB_RJ", ("U2", "3"), ("C4", "1"))
L04.net("+3V3", ("U2", "5"), ("C5", "1"))
L04.net("GND", ("U2", "2"), ("C4", "2"), ("C5", "2"))
# U2 pin 8 (S, split-termination stabilization output) is intentionally
# unused -- termination is Hub-only (spec Sec 3.1); left with no net so the
# generic pass emits its no_connect, matching every module in this repo.
L04.hier_exports = {
    "CAN_H_RJ":  ("output", ("FL1", "1")),
    "CAN_L_RJ":  ("output", ("FL1", "2")),
    "CAN_TX":    ("output", ("U2", "1")),
    "CAN_RX":    ("output", ("U2", "4")),
}
# +5VSB_RJ is the GLOBAL bus (see 03-hub-link's identical note).


# ===========================================================================
# 07 -- usb-flash: USB-C 2.0 flash/debug + H3 standalone-mode USB ESD/EMC
#       suite (USBLC6-2SC6 + VBUS bead + discrete VBUS PESD clamp). Spec
#       Sec 6.14/7.5. USB is a DATA path + bench-flash power only, NEVER the
#       LED power feed (spec-explicit) -- VBUS only reaches 05-mcu's logic OR.
# ===========================================================================
L07 = LEAVES["07-usb-flash"]
ap(L07, "J3", "cec-vendor", "USB_C_Receptacle_USB2.0_16P", "USB-C 2.0",
   "cec-Connector_USB:USB_C_Receptacle_XKB_U262-16XN-4BVC11",
   {"Manufacturer": "XKB Connectivity", "MPN": "U262-161N-4BVC11", "LCSC": "C319148"})
ap(L07, "D5", "cec-vendor", "D_Schottky", "PESD5V0S1BA", "cec-Diode_SMD:D_SOD-323",
   {"Manufacturer": "Nexperia", "MPN": "PESD5V0S1BA", "LCSC": "C5261083",
    "Description": "Discrete VBUS clamp, ahead of the entry bead (H3a posture)"})
ap(L07, "D6", "cec-vendor", "USBLC6-2SC6", "USBLC6-2SC6",
   "cec-Package_TO_SOT_SMD:SOT-23-6",
   {"Manufacturer": "onsemi", "MPN": "USBLC6-2SC6", "LCSC": "C2687116"})
ap(L07, "FB2", "cec-vendor", "FerriteBead_Small", "600R@100MHz FB (MPZ2012S601AT000)",
   "cec-Capacitor_SMD:C_0805_2012Metric",
   {"Manufacturer": "TDK", "MPN": "MPZ2012S601AT000", "LCSC": "C21519",
    "Description": "VBUS entry bead, POPULATED (H3a ferrite posture (a))"})
ap(L07, "C10", "cec-vendor", "C_Small", "10u", "cec-Capacitor_SMD:C_0805_2012Metric",
   {"Manufacturer": "Samsung", "MPN": "CL21A106KAYNNNE", "LCSC": "C15850"})
ap(L07, "R18", "cec-vendor", "R_Small", "5k1", "cec-Resistor_SMD:R_0402_1005Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF5101TCE", "LCSC": "C25905"})
ap(L07, "R19", "cec-vendor", "R_Small", "5k1", "cec-Resistor_SMD:R_0402_1005Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF5101TCE", "LCSC": "C25905"})

L07.net("VBUS_RAW", ("J3", "A4"), ("J3", "A9"), ("J3", "B4"), ("J3", "B9"),
        ("D5", "1"), ("D6", "5"), ("FB2", "1"))
L07.net("VBUS", ("FB2", "2"), ("C10", "1"))
L07.net("USB_D_P", ("J3", "A6"), ("J3", "B6"), ("D6", "1"), ("D6", "6"))
L07.net("USB_D_N", ("J3", "A7"), ("J3", "B7"), ("D6", "3"), ("D6", "4"))
L07.net("USB_CC1", ("J3", "A5"), ("R18", "1"))
L07.net("USB_CC2", ("J3", "B5"), ("R19", "1"))
L07.net("GND", ("J3", "A1"), ("J3", "A12"), ("J3", "B1"), ("J3", "B12"), ("J3", "S1"),
        ("D5", "2"), ("D6", "2"), ("C10", "2"), ("R18", "2"), ("R19", "2"))
L07.hier_exports = {
    "USB_D_P": ("output", ("D6", "1")),
    "USB_D_N": ("output", ("D6", "3")),
    "VBUS":    ("output", ("FB2", "2")),
}
# GND needs no powerflag_nets entry here either -- see 03-hub-link's note
# (01-power-input's single flag covers the whole project-wide GND net).
L07.powerflag_nets = []


# ===========================================================================
# 05 -- mcu: ESP32-S3-MINI-1-N4R2 + BOOT/RESET + 3-way logic-power diode-OR
#       (SATA-derived +5V_LED, USB VBUS, RJ-45 5VSB -- OQ/README-flagged
#       proposal on the 3rd leg) -> LP5907 3V3 LDO.
# ===========================================================================
L05 = LEAVES["05-mcu"]
ap(L05, "U1", "cec-vendor", "ESP32-S3-MINI-1", "ESP32-S3-MINI-1-N4R2",
   "cec-RF_Module:ESP32-S2-MINI-1_NoAntKeepout",
   {"Manufacturer": "Espressif", "MPN": "ESP32-S3-MINI-1-N4R2", "LCSC": "C3013941",
    "Description": "Working-basis MCU (OQ-29 OPEN, platform-wide) -- LCD/I2S "
                   "parallel peripheral drives all 8 WS2812-class channels with "
                   "low jitter; same exact part already used on 12VHPWR-Standard. "
                   "OOS at LCSC as of 2026-07-05 (docs/pricing-study-2026-07-05.md), "
                   "owner ratifies. See README.md Sec 1."})
ap(L05, "U3", "cec-vendor", "LP5907MFX-1.2", "LP5907MFX-3.3",
   "cec-Package_TO_SOT_SMD:SOT-23-5",
   {"Manufacturer": "Texas Instruments", "MPN": "LP5907MFX-3.3", "LCSC": "C80670"})
# NOTE: lib symbol name is the BASE "LP5907MFX-1.2" -- the "LP5907MFX-3.3"
# library entry is a KiCad (extends "LP5907MFX-1.2") variant stub with no
# pins/graphics of its own, which this repo's cec_sch pin-table tooling does
# not resolve. Same precedent as modules/ent-common/gen_p4_t1_block.py:188
# (name=base symbol, value=the real 3.3V part) -- BOM/props below carry the
# correct MPN/LCSC for the actual 3.3V part, only the lib_id points at the
# pin-bearing base symbol (identical pinout across the LP5907MFX-x.x family).
ap(L05, "C6", "cec-vendor", "C_Small", "10u", "cec-Capacitor_SMD:C_0805_2012Metric",
   {"Manufacturer": "Samsung", "MPN": "CL21A106KAYNNNE", "LCSC": "C15850"})
ap(L05, "C7", "cec-vendor", "C_Small", "1u", "cec-Capacitor_SMD:C_0603_1608Metric",
   # LCSC C29936 (not the earlier C15849, measured bug fixed): C15849 is
   # actually CL10A105KB8NNNC (a different, though electrically similar,
   # Samsung 1uF 0603) on the live LCSC listing, not the intended
   # CL10B105KA8NNNC -- C29936 is the correct listing (cross-checked against
   # another board's own sourced BOM). Same fix applies to C8/C9 below.
   {"Manufacturer": "Samsung", "MPN": "CL10B105KA8NNNC", "LCSC": "C29936"})
ap(L05, "C39", "cec-vendor", "C_Small", "100n", "cec-Capacitor_SMD:C_0402_1005Metric",
   {"Manufacturer": "Samsung", "MPN": "CL05B104KO5NNNC", "LCSC": "C1525"})
ap(L05, "C8", "cec-vendor", "C_Small", "1u", "cec-Capacitor_SMD:C_0603_1608Metric",
   {"Manufacturer": "Samsung", "MPN": "CL10B105KA8NNNC", "LCSC": "C29936",
    "Description": "LDO IN bulk"})
ap(L05, "C9", "cec-vendor", "C_Small", "1u", "cec-Capacitor_SMD:C_0603_1608Metric",
   {"Manufacturer": "Samsung", "MPN": "CL10B105KA8NNNC", "LCSC": "C29936",
    "Description": "LDO OUT bulk"})
ap(L05, "R8", "cec-vendor", "R_Small", "10k", "cec-Resistor_SMD:R_0402_1005Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF1002TCE", "LCSC": "C25744",
    "Description": "EN pullup"})
ap(L05, "R9", "cec-vendor", "R_Small", "10k", "cec-Resistor_SMD:R_0402_1005Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF1002TCE", "LCSC": "C25744",
    "Description": "GPIO0/BOOT pullup"})
ap(L05, "SW1", "cec-vendor", "SW_Push", "BOOT", "cec-Button_Switch_SMD:TS-1088-AR02016",
   {"Manufacturer": "XKB", "MPN": "TS-1088-AR02016", "LCSC": "C720477"})
ap(L05, "SW2", "cec-vendor", "SW_Push", "RESET", "cec-Button_Switch_SMD:TS-1088-AR02016",
   {"Manufacturer": "XKB", "MPN": "TS-1088-AR02016", "LCSC": "C720477"})
ap(L05, "D2", "cec-vendor", "D_Schottky", "SS34", "cec-Diode_SMD:D_SMA",
   {"Manufacturer": "MDD", "MPN": "SS34", "LCSC": "C8678",
    "Description": "Logic-power OR: +5V_LED (SATA-derived) leg"})
ap(L05, "D3", "cec-vendor", "D_Schottky", "SS34", "cec-Diode_SMD:D_SMA",
   {"Manufacturer": "MDD", "MPN": "SS34", "LCSC": "C8678",
    "Description": "Logic-power OR: RJ-45 5VSB leg (PROPOSAL -- see README.md Sec 3)"})
ap(L05, "D4", "cec-vendor", "D_Schottky", "SS34", "cec-Diode_SMD:D_SMA",
   {"Manufacturer": "MDD", "MPN": "SS34", "LCSC": "C8678",
    "Description": "Logic-power OR: USB VBUS leg"})

L05.net("+5V_LED", ("D2", "2"))
L05.net("+5VSB_RJ", ("D3", "2"))
L05.net("VBUS", ("D4", "2"))
L05.net("+5V_LOGIC_OR", ("D2", "1"), ("D3", "1"), ("D4", "1"), ("U3", "1"), ("U3", "3"),
        ("C8", "1"))   # U3.3 = LP5907 EN, strapped to IN (always-on; ent-common precedent)
L05.net("+3V3", ("U3", "5"), ("C9", "1"), ("C6", "1"), ("C7", "1"), ("C39", "1"),
        ("R8", "1"), ("R9", "1"), ("U1", "3"))
L05.net("GND", ("U3", "2"), ("C6", "2"), ("C7", "2"), ("C39", "2"), ("C8", "2"), ("C9", "2"),
        ("SW1", "2"), ("SW2", "2"),
        ("U1", "1"), ("U1", "2"), ("U1", "42"), ("U1", "43"), ("U1", "46"),
        *[("U1", str(n)) for n in range(47, 66)])
# SW_Push is a plain 2-pin momentary switch (pin1/pin2 symmetric, shorted
# when pressed) -- pin1 of EACH button is wired to its own signal's
# pullup/MCU node (EN for SW2, GPIO0 for SW1; see compose_mcu), pin2 to
# GND, so a press pulls the signal low. (Corrected: an earlier version had
# this backwards -- SW1.1/SW2.1 listed under GND while compose_mcu's real
# wiring put pin1 on the SIGNAL node, and pin2 was left un-wired entirely
# under the wrong "signal" listing -- the boot/reset buttons' GND return
# was completely missing. ERC's isolated_pin_label on GPIO0 was the first
# visible symptom.)
L05.net("EN", ("U1", "45"), ("R8", "2"), ("SW2", "1"))
L05.net("GPIO0", ("U1", "4"), ("R9", "2"), ("SW1", "1"))
L05.net("USB_D_P", ("U1", "24"))
L05.net("USB_D_N", ("U1", "23"))
L05.net("CAN_TX", ("U1", "21"))
L05.net("CAN_RX", ("U1", "22"))
L05.net("DETECT_SENSE", ("U1", "16"))
L05.net("ISENSE_TOTAL", ("U1", "5"))
L05.net("VRAIL_5V_DIV", ("U1", "6"))
L05.net("LED1_DATA", ("U1", "8"))
L05.net("LED2_DATA", ("U1", "9"))
L05.net("LED3_DATA", ("U1", "10"))
L05.net("LED4_DATA", ("U1", "11"))
L05.net("LED5_DATA", ("U1", "12"))
L05.net("LED6_DATA", ("U1", "13"))
L05.net("LED7_DATA", ("U1", "14"))
L05.net("LED8_DATA", ("U1", "15"))
L05.net("STATUS_LED_DATA", ("U1", "25"))
# NOTE: U1's pin map (IO1/IO2 ADC1 sense; IO4-IO11 LED data; IO12 DETECT_SENSE
# (ADC2); IO17/IO18 CAN; IO21 status LED) is a WORKING BASIS like every other
# CEC module's GPIO assignment -- the ESP32-S3 GPIO matrix + LCD/I2S parallel
# peripheral bind to any of these pins in firmware, so exact numbers are not
# schematic-locked. Chosen to avoid every strapping pin (IO0/IO3/IO45/IO46)
# and the SPI-flash-shared pins (IO26-IO32), matching the platform's existing
# 12VHPWR-Standard convention for CAN_TX/RX (IO17/IO18) and EN/GPIO0/USB
# (native fixed pins).
L05.hier_exports = {
    "VBUS":            ("output", ("D4", "2")),
    "CAN_TX":          ("output", ("U1", "21")),
    "CAN_RX":          ("output", ("U1", "22")),
    "DETECT_SENSE":    ("output", ("U1", "16")),
    "ISENSE_TOTAL":    ("output", ("U1", "5")),
    "VRAIL_5V_DIV":    ("output", ("U1", "6")),
    "USB_D_P":         ("output", ("U1", "24")),
    "USB_D_N":         ("output", ("U1", "23")),
    "LED1_DATA":       ("output", ("U1", "8")),
    "LED2_DATA":       ("output", ("U1", "9")),
    "LED3_DATA":       ("output", ("U1", "10")),
    "LED4_DATA":       ("output", ("U1", "11")),
    "LED5_DATA":       ("output", ("U1", "12")),
    "LED6_DATA":       ("output", ("U1", "13")),
    "LED7_DATA":       ("output", ("U1", "14")),
    "LED8_DATA":       ("output", ("U1", "15")),
    "STATUS_LED_DATA": ("output", ("U1", "25")),
}
L05.powerflag_nets = []
# +5V_LOGIC_OR's PWR_FLAG is stamped directly in compose_mcu at U3.1's own
# already-wired point (not via powerflag_nets -- see that stamp's comment
# for why the anchor-block mechanism doesn't reach this particular net).


# ===========================================================================
# 06 -- led-outputs: ONE 74AHCT244 (VCC=+5V_LED) level-shifts all 8 channels;
#       per channel after the buffer: series R -> BAT54S DATA-first hot-plug
#       clamp -> PESD5V0S1BA TVS -> ARGB header. Spec Sec 7.3 (LOCKED approach).
# ===========================================================================
L06 = LEAVES["06-led-outputs"]
ap(L06, "U5", "cec-vendor", "74AHCT244", "SN74AHCT244PW",
   "cec-Package_SO:TSSOP-20_L6.5-W4.4-P0.65-LS6.4-BL",
   {"Manufacturer": "Nexperia", "MPN": "74AHCT244PW,118", "LCSC": "C135583",
    "Description": "Octal buffer/line driver, non-inverting, 3-state -- TTL "
                   "input threshold (~2V) so 3.3V MCU drive is in-spec at a "
                   "5V supply (spec Sec 7.3)"})

# 74AHCT244 channel map (JEDEC-standard pinout, VERIFIED against the real
# vendored part -- see the pin dump in the session's research): channel k's
# input/output pin PAIRS, in the physical order the octal buffer presents
# them (NOT simply 1..8 -- the part interleaves its two 4-bit groups).
_AHCT244_CH = {
    1: ("2", "18"), 2: ("4", "16"), 3: ("6", "14"), 4: ("8", "12"),
    5: ("17", "3"), 6: ("15", "5"), 7: ("13", "7"), 8: ("11", "9"),
}

_5v_led_members = [("U5", "20")]
_gnd_members = [("U5", "10"), ("U5", "1"), ("U5", "19")]
_hier_exports_06 = {}

for _ch in range(1, 9):
    _in_pin, _out_pin = _AHCT244_CH[_ch]
    _r, _dclamp, _dtvs, _j = f"R{9 + _ch}", f"D{6 + _ch}", f"D{14 + _ch}", f"J{3 + _ch}"

    # LCSC C25104 (not the earlier C25131, measured bug fixed): C25131 is
    # actually 0402WGF680JTCE (68R) on the live LCSC listing, not the
    # intended 330R 0402WGF3300TCE -- would have shipped the wrong series-
    # resistor value on all 9 LED-channel/status-LED positions using this
    # value (R10-R17 below + R20 in 08-status).
    ap(L06, _r, "cec-vendor", "R_Small", "330",
       "cec-Resistor_SMD:R_0402_1005Metric",
       {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF3300TCE", "LCSC": "C25104",
        "Description": f"LED channel {_ch} series resistor"})
    ap(L06, _dclamp, "cec-vendor", "BAT54S", "BAT54S",
       "cec-Package_TO_SOT_SMD:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-TL",
       {"Manufacturer": "UMW", "MPN": "BAT54S", "LCSC": "C545549",
        "Description": f"LED channel {_ch} DATA-first hot-plug clamp (dual-series "
                       "Schottky, pin1=anode/pin3=tap/pin2=cathode -- VERIFIED by "
                       "rendering the vendored symbol, see README.md Sec 4. Spec "
                       "names BAT54W, which is not a real dual-diode part under "
                       "that name; BAT54S is the verified series-diode part that "
                       "implements the described clamp)"})
    ap(L06, _dtvs, "cec-vendor", "D_Schottky", "PESD5V0S1BA",
       "cec-Diode_SMD:D_SOD-323",
       {"Manufacturer": "Nexperia", "MPN": "PESD5V0S1BA", "LCSC": "C5261083",
        "Description": f"LED channel {_ch} per-line ESD TVS"})
    ap(L06, _j, "cec-Connector_Generic", "Conn_01x04", "ARGB_5V_HDR",
       "cec-Connector_PinHeader_2.54mm:HDR-TH_4P-P2.54-V-M",
       {"Manufacturer": "Ckmtw", "MPN": "B-2100S04P-A110", "LCSC": "C124378",
        "Description": f"LED channel {_ch} ARGB strip header -- plain 1x4 2.54mm, "
                       "pin 2 left NC (real keyed 4-pos/3-used ARGB part does not "
                       "exist on LCSC; OQ-36, see README.md)"})

    # buffer input (from 05-mcu, hier_export, SAME name as that leaf's own
    # export so build_thin_parent pairs the two as one 2-leaf lane). 06
    # RECEIVES this signal (05-mcu drives it) -- role is "input" here.
    L06.net(f"LED{_ch}_DATA", ("U5", _in_pin))
    _hier_exports_06[f"LED{_ch}_DATA"] = ("input", ("U5", _in_pin))
    # R's upstream (from U5) vs downstream (to dclamp) PIN NUMBER swaps
    # between the two 74AHCT244 mirror groups (compose_led_outputs picks
    # this per-channel from the real pin_out() geometry; ch1-4 = group1,
    # sgn=+1, pin1=upstream/pin2=downstream, ch5-8 = group2 (MIRRORED),
    # sgn=-1, swapped) -- mirrored here with the same static ch<=4 split so
    # the net membership matches whichever physical pin compose_led_outputs
    # actually wires (measured bug, fixed: this net list hardcoded
    # pin1=upstream/pin2=downstream for EVERY channel, which was wrong for
    # the mirrored group and produced a downstream wire that had to cross
    # back through R's own body to reach the correctly-declared pin --
    # audit-sch.py's wire_through_body caught it on R14-R17).
    _r_up, _r_dn = ("1", "2") if _ch <= 4 else ("2", "1")
    # buffer output (5V level), leaf-internal only
    L06.net(f"LED{_ch}_BUF", ("U5", _out_pin), (_r, _r_up))
    # post-series-resistor node: BAT54S tap (pin3) + PESD anode-side (pin1,
    # signal) + header DATA pin, leaf-internal only
    L06.net(f"LED{_ch}_HDR", (_r, _r_dn), (_dclamp, "3"), (_dtvs, "1"), (_j, "3"))

    _5v_led_members += [(_dclamp, "2"), (_j, "1")]     # BAT54S pin2 = cathode -> +5V_LED
    _gnd_members += [(_dclamp, "1"), (_dtvs, "2"), (_j, "4")]  # BAT54S pin1 = anode -> GND
    # J pin 2 is the real ARGB standard's removed/keyed position -- left with
    # no net, generic pass emits its no_connect (see README.md Sec 5/OQ-36).

L06.net("+5V_LED", *_5v_led_members)
L06.net("GND", *_gnd_members)

L06.hier_exports = _hier_exports_06
L06.powerflag_nets = []


# ===========================================================================
# 08 -- status: ONE SK6812MINI status pixel (platform LED language), level-
#       shifted the same way Hub Standard's own on-board LED chain is (a
#       single SN74AHCT1G08 2-input AND with both inputs tied = a non-
#       inverting 3.3V->5V buffer) -- included per the brief's "your call",
#       populated (not DNP): cheap, simple, reuses an EXISTING proven CEC
#       circuit verbatim, and a standalone-mode board benefits the most from
#       a local health indicator with no Hub/host present to show one.
# ===========================================================================
L08 = LEAVES["08-status"]
ap(L08, "U6", "cec-vendor", "SN74AHCT1G08", "SN74AHCT1G08",
   "cec-Package_TO_SOT_SMD:SOT-23-5",
   {"Manufacturer": "Texas Instruments", "MPN": "SN74AHCT1G08DBVR", "LCSC": "C113521",
    # measured bug, fixed: C7526 (an earlier value here) 404s on the live
    # LCSC listing -- C113521 is the Hub Standard's own sourced LCSC number
    # for the identical SN74AHCT1G08DBVR (hub-standard/bom/bom.csv, U6),
    # verified against the live LCSC listing to be the right part.
    "Description": "2-input AND, both inputs tied = non-inverting 3.3V->5V "
                   "level shift for the SK6812 DIN (Hub Standard's own U6 "
                   "precedent, verbatim)"})
ap(L08, "DL1", "cec-vendor", "SK6812MINI", "SK6812MINI",
   "cec-LED_SMD:LED_SK6812MINI_PLCC4_3.5x3.5mm_P1.75mm",
   {"Manufacturer": "Opsco", "MPN": "SK6812MINI-E", "LCSC": "C5149201",
    # measured bug, fixed: C2841455 (an earlier value here) is NOT this LED --
    # verified against the live LCSC listing it is a VIIYONG 4.7pF 0201
    # ceramic cap, an unrelated part. C5149201 is the Hub Standard's own
    # sourced LCSC number for the identical SK6812MINI-E (hub-standard/bom/
    # bom.csv, DL1-DL7), verified against the live LCSC listing to be the
    # right part.
    "Description": "Status pixel, platform LED language"})
ap(L08, "R20", "cec-vendor", "R_Small", "330", "cec-Resistor_SMD:R_0402_1005Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF3300TCE", "LCSC": "C25104"})
ap(L08, "C11", "cec-vendor", "C_Small", "100n", "cec-Capacitor_SMD:C_0402_1005Metric",
   {"Manufacturer": "Samsung", "MPN": "CL05B104KO5NNNC", "LCSC": "C1525"})

L08.net("STATUS_LED_DATA", ("U6", "1"), ("U6", "2"))
L08.net("STATUS_LED_BUF", ("U6", "4"), ("R20", "1"))
L08.net("STATUS_LED_DIN", ("R20", "2"), ("DL1", "3"))
L08.net("+5V_LED", ("U6", "5"), ("C11", "1"), ("DL1", "4"))
L08.net("GND", ("U6", "3"), ("C11", "2"), ("DL1", "2"))
# DL1 pin1 (DOUT) is the daisy-chain output -- this is the only pixel on the
# chain, left with no net (generic pass emits its no_connect).
L08.hier_exports = {
    "STATUS_LED_DATA": ("output", ("U6", "1")),
}
L08.powerflag_nets = []


# ===========================================================================
# COMPOSED LAYOUTS -- 1.27mm grid units, cec_sch_compose.Compose convention.
# ===========================================================================
def _grid_place(c, refs, x0, y0, cols, dx=16, dy=16):
    for i, ref in enumerate(refs):
        c.place(ref, x0 + (i % cols) * dx, y0 + (i // cols) * dy)


def compose_power_input(c, lf):
    c.place("J1", 20, 50)
    # bus the three SATA +5V pins (7,8,9) to a shared vertical spine, then
    # right into Q1's three paralleled source pins
    p7, p8, p9 = c.pin("J1", "7"), c.pin("J1", "8"), c.pin("J1", "9")
    busx = p7[0] - 10
    c.wire(p7, (busx, p7[1]))
    c.wire(p8, (busx, p8[1]))
    c.wire(p9, (busx, p9[1]))
    # p8 (the Y-middle pin) is a TRUE SHARED ENDPOINT of two bus segments
    # (p7-p8, p8-p9) rather than an interior tap of one continuous p7-to-p9
    # run (measured bug, fixed): a later bridge wire ALSO needs to start
    # exactly at p8's point (see srcbusx below) to reach Q1's source, and
    # with the single-continuous-run version that made THREE separate wire
    # objects converge on one WIRE'S INTERIOR point (only p8's own stub
    # was a true endpoint there) -- the exported netlist showed p7/p9
    # split off from p8/Q1 into two disconnected nets even though every
    # coordinate nominally coincided. Splitting the bus so p8's point is a
    # genuine shared endpoint of every wire touching it resolves it.
    c.wire((busx, p7[1]), (busx, p8[1]))
    c.wire((busx, p8[1]), (busx, p9[1]))
    c.use(("J1", "7"), ("J1", "8"), ("J1", "9"))

    # Q1 rot=270 (CHANGED from 90 -- measured bug, fixed): at rot90 the
    # source pins (1,2,3) sit on Q1's RIGHT (u_x=56) and drain (5,6,7,8) on
    # its LEFT (u_x=44) -- backwards from the SATA(left)->source->drain->
    # F1(right) flow, forcing the drain bus back across the source bus's
    # own X-range (u_x 50-56). A drain-bus wire's own endpoint (from pin7,
    # the max-Y drain pin) landed exactly inside the source bus's Y=52
    # horizontal run's interior -- an unintended T-junction SHORTING THE
    # FET'S SOURCE TO ITS OWN DRAIN, defeating the whole reverse-polarity
    # protection (measured via the exported netlist: Q1 pins 1-3 AND 5-8
    # all merged into one node with F1/J1 -- not merely an ERC nuisance).
    # At rot=270, source(1,2,3) is on the LEFT (u_x=44, facing J1) and
    # drain(5,6,7,8) on the RIGHT (u_x=56, facing F1) -- a clean monotonic
    # left-to-right flow with no bus crossing possible.
    c.place("Q1", 50, 50, 270)
    q1, q2, q3 = c.pin("Q1", "1"), c.pin("Q1", "2"), c.pin("Q1", "3")
    srcbusx = busx + 30
    # J1 (a 15-pin SATA connector) draws its own body as a rectangle
    # spanning the FULL pin1-to-pin15 height -- every one of its pins,
    # including p8, sits inside that box's own Y-range by construction, so
    # a naive straight bridge from busx (left of the body) to srcbusx
    # (right of it) at p8's own Y cuts straight across the body (measured:
    # audit-sch.py wire_through_body). busx/srcbusx are ALREADY clear of
    # the body in X (busx left of it, srcbusx right of it) -- only the
    # horizontal crossing at a body-spanned Y is the problem -- so detour
    # up to a Y clear of the body's top (pin1) before crossing, then back
    # down to p8's Y on the far side (also body-clear in X there).
    bridge_y = 25
    c.wire((busx, p8[1]), (busx, bridge_y), (srcbusx, bridge_y), (srcbusx, p8[1]))
    # q1 happens to share p8's own Y (both =50) -- a "jog" via an
    # intermediate (srcbusx, q1[1]) point would be a ZERO-LENGTH wire
    # segment (measured bug, fixed: KiCad's connectivity did not propagate
    # through that degenerate segment, splitting J1.7/J1.9 off from J1.8/
    # Q1.1-3 into two separate isolated nets even though every coordinate
    # was nominally "coincident" -- exported-netlist verified). Route q1
    # directly with no redundant same-point jog; q2/q3 genuinely need theirs
    # (different Y).
    c.wire((srcbusx, p8[1]), q1)
    c.wire((srcbusx, p8[1]), (srcbusx, q2[1]), q2)
    c.wire((srcbusx, p8[1]), (srcbusx, q3[1]), q3)
    c.use(("Q1", "1"), ("Q1", "2"), ("Q1", "3"))
    q5, q6, q7, q8 = (c.pin("Q1", "5"), c.pin("Q1", "6"),
                      c.pin("Q1", "7"), c.pin("Q1", "8"))
    dbusx = q5[0] + 8
    for p in (q5, q6, q7, q8):
        c.wire(p, (dbusx, p[1]))
    # measured Y order q7(48) < q5(50) < q6(52) < q8(54) -- one vertical run
    # spanning the full min-to-max (q7 to q8) passes through q5/q6's stub
    # endpoints too (a stub landing on the spine's interior is still
    # electrically joined). (Corrected: an earlier version of this comment
    # and span mislabeled q6 as the minimum -- it is actually q7 -- and the
    # resulting q6-to-q8 span [52,54] missed both q7(48) and q5(50),
    # leaving q7 fully unconnected per the exported netlist.)
    c.wire((dbusx, q7[1]), (dbusx, q8[1]))
    c.use(("Q1", "5"), ("Q1", "6"), ("Q1", "7"), ("Q1", "8"))
    qg = c.pin("Q1", "4")
    c.place("R1", qg[0], qg[1] - 12)
    r1_2 = c.pin("R1", "2")
    c.wire(qg, r1_2)
    c.use(("Q1", "4"), ("R1", "2"))

    c.place("F1", 75, 50)
    f1, f2 = c.pin("F1", "1"), c.pin("F1", "2")
    c.wire((dbusx, q6[1]), (dbusx, f1[1]), f1)
    c.use(("F1", "1"))

    c.place("RT1", 95, 50)
    rt1, rt2 = c.pin("RT1", "1"), c.pin("RT1", "2")
    c.wire(f2, rt1)
    c.use(("F1", "2"), ("RT1", "1"))

    # +5V_LED_IN spine: RT1 out -> a T-junction feeding (a) bulk cap C1 below,
    # (b) the divider top R2 further below still, (c) a SEPARATE, clear-Y
    # exit row up top for the io-column (so the rightward exit lane never
    # runs through R2/R3/C2's bodies -- measured collision, fixed by giving
    # the exit its own row instead of sharing R2's Y).
    G_ = cec_sch.GRID
    spine_y = rt2[1]
    tx = rt2[0] + 8
    exit_y = spine_y - 20
    c.wire(rt2, (tx, spine_y))
    c.wire((tx, spine_y), (tx, exit_y))
    c.io("+5V_LED_IN", "right", from_pt=(tx, exit_y))

    c.place("C1", tx, 70)
    c1p1 = c.pin("C1", "1")
    c.wire((tx, spine_y), (tx, c1p1[1]), c1p1)
    c.use(("RT1", "2"), ("C1", "1"))

    divy = 90
    mid = arch.divider_chain(c, "R2", "R3", 130, divy, tap="VRAIL_5V_DIV",
                              tap_ang=0, tap_kind="hier")
    r2p1 = c.pin("R2", "1")
    c.wire((tx, spine_y), (tx, divy - 2), (r2p1[0], divy - 2), r2p1)
    c.use(("R2", "1"))
    c.place("C2", 155, divy + 4)
    c.wire(mid, (155, mid[1]))
    c2p1 = c.pin("C2", "1")
    c.wire((155, mid[1]), (155, c2p1[1]), c2p1)
    c.use(("C2", "1"))

    c.caption("SATA IN -> reverse-polarity P-FET -> PPTC fuse -> NTC inrush "
              "-> +5V_LED_IN (spec Sec 7.2)", 10, 8)
    c.note("Q1 gate pulldown R1=10k (Vgs=-5V forward, 0V reverse -- blocks a "
           "miswired feed); RT1/F1/Q1 values are a working basis, see README.md",
           10, 90)
    c.done()


def compose_sense(c, lf):
    # RS1 (shunt) and U4 (INA180A2) are placed close together (short Kelvin
    # taps). +5V_LED_IN's TWO members (RS1.1, the shunt HI/upstream terminal,
    # AND U4.3/IN+, the INA180's non-inverting input tapping that same
    # terminal) are the SAME physical node -- draw the short local jog
    # explicitly between them (measured bug, fixed: leaving U4.3 unconsumed
    # let the generic per-pin pass auto-place its "+5V_LED_IN" label
    # independently, and it landed on the SAME Y-row as ISENSE_TOTAL's own
    # default-anchor routing from U4.1 -- the two unrelated nets shared a
    # wire and ERC correctly flagged "multiple_net_names", merging
    # +5V_LED_IN and ISENSE_TOTAL into one net). Every member of the
    # +5V_LED GLOBAL bus (RS1.2/U4.4/U4.5/C3.1) is still left to the generic
    # per-pin pass -- an independent global_label stub at each is correct by
    # design (global labels of the same name merge project-wide with no
    # local wire needed); only the two LANE-ROUTED hier_exports (+5V_LED_IN,
    # ISENSE_TOTAL) needed an explicit anchor each.
    c.place("RS1", 30, 30, 90)
    c.place("U4", 60, 30)
    c.place("C3", 60, 55)

    # RS1 (rot90) spans u=(29,31)x(27,33); U4 spans u=(56,64)x(24,36); U4's
    # pins 1/2/3 (OUT/GND/IN+) all sit on the SAME row u_y=38, at u_x=58/60/62
    # respectively -- routing RS1.1 (u=30,35) straight across to U4.3 (u=62,38)
    # at a naive Y would either cut through U4's body or through pins 1/2 on
    # that shared row. Measured-clear jog: drop to Y=39 (below BOTH bodies --
    # RS1 bottom 33, U4 bottom 36 -- and off the 38-row so it approaches U4.3
    # from below, not through pins 1/2).
    rs1_1 = c.pin("RS1", "1")
    u4_3 = c.pin("U4", "3")
    c.wire(rs1_1, (rs1_1[0], 39), (u4_3[0], 39), u4_3)
    c.io("+5V_LED_IN", "left", from_pt=(rs1_1[0], rs1_1[1]))
    c.use(("RS1", "1"), ("U4", "3"))

    # U4.1 (OUT/ISENSE_TOTAL) is the LEFTMOST of that same shared 38-row
    # (pins 2/3 sit further right on the identical Y) -- routing it "right"
    # directly would cut straight through pins 2 and 3. Drop clear of the
    # row first (Y=45, comfortably below U4's body too), then export right
    # from there.
    u4_1 = c.pin("U4", "1")
    c.wire(u4_1, (u4_1[0], 45))
    c.io("ISENSE_TOTAL", "right", from_pt=(u4_1[0], 45))
    c.use(("U4", "1"))

    # +5V_LED is entirely diode/shunt/passive-fed (no local "power_out" pin
    # anywhere the GLOBAL bus touches across 02-sense/05-mcu/06-led-outputs/
    # 08-status), so ERC's power_pin_not_driven fires on every downstream
    # Power-input pin (05-mcu's U3.1, 08-status's DL1.4). A PWR_FLAG stamped
    # exactly at RS1.2's own point (left UNCONSUMED, so it still separately
    # gets its own global_label stub) marks the bus externally driven
    # without creating a second, disconnected island -- same pattern as
    # +5VSB_RJ's anchor in 03-hub-link.
    rs1_2 = c.pin("RS1", "2")
    c.stamp("PWR_FLAG", rs1_2[0], rs1_2[1], 0)

    c.caption("Total-rail shunt + INA180A2 (50V/V) -> +5V_LED (spec Sec 7.4)", 10, 4)
    c.note("+5V_LED members (RS1.2/U4 VS+IN-/C3) are plain same-name global "
           "labels -- the shunt's own terminal copper IS the Kelvin tap "
           "(layout, Sec 6.8)", 10, 70)
    c.done()


def compose_hub_link(c, lf):
    c.place("J2", 20, 50)
    j1, j2, j3, j6, j8 = (c.pin("J2", "1"), c.pin("J2", "2"), c.pin("J2", "3"),
                          c.pin("J2", "6"), c.pin("J2", "8"))
    # J2's body spans Y=42-58 (measured from the symbol) -- pins 3/6 sit just
    # left of it (X=12 vs body X=16-24), so routing straight right from
    # either pin would cut through J2's OWN body. Jog up to Y<42 first (clear
    # above), matching J1's own wire to FB1 below.
    c.wire(j3, (j3[0], 30))
    c.io("CAN_H_RJ", "right", from_pt=(j3[0], 30))
    c.use(("J2", "3"))
    c.wire(j6, (j6[0], 34))
    c.io("CAN_L_RJ", "right", from_pt=(j6[0], 34))
    c.use(("J2", "6"))

    # VCC_RJ45_RAW -> FB1 (5VSB entry bead) -> +5VSB_RJ. FB1.2 is left
    # UNCONSUMED: +5VSB_RJ is a GLOBAL bus (03/04/05, a genuine 3-leaf net),
    # so it gets its own global_label stub from the generic per-pin pass,
    # same as +5V_LED elsewhere (see 02-sense's note).
    c.place("FB1", 45, 20)
    fb1a = c.pin("FB1", "1")
    c.wire(j1, (j1[0], fb1a[1]), fb1a)
    c.use(("J2", "1"), ("FB1", "1"))
    # +5VSB_RJ is fed entirely from the RJ-45 cable through a passive bead
    # (FB1) -- no local pin anywhere on this GLOBAL bus is an actual
    # "power_out" type, so ERC's power_pin_not_driven fires on every
    # downstream Power-input pin (04-can's U2.3, matching ent-common's
    # identical "+5VSB" precedent). A PWR_FLAG stamped exactly at FB1.2's
    # own point (left UNCONSUMED, so it still separately gets its own
    # global_label stub) marks the bus externally driven without creating
    # a second, disconnected island.
    fb1b = c.pin("FB1", "2")
    c.stamp("PWR_FLAG", fb1b[0], fb1b[1], 0)

    # DETECT chain: J2.8 drops well clear of pins 3/6 (whose CAN_H_RJ/CAN_L_RJ
    # io lanes travel the full sheet width at THEIR row) before running the
    # chain -- D1 (ESD, shunt to GND) -- R4 (2.2k code, shunt to GND) -- R5
    # (100k poke tap, series) -- DETECT_SENSE (exit right).
    chain_y = j8[1] + 40
    c.wire(j8, (j8[0], chain_y))
    end = arch.protection_chain(
        c, (j8[0], chain_y),
        [("shunt", "D1"), ("shunt", "R4"), ("series", "R5")],
        "DETECT_SENSE", out_kind="none", node_label="DETECT", pitch=8)
    c.use(("J2", "8"))
    c.io("DETECT_SENSE", "right", from_pt=end)

    c.caption("RJ-45 FTP + DETECT (2.2k CAN-only code) + 5VSB entry bead "
              "(spec Sec 2.1/2.3/2.4/7.5)", 10, 8)
    c.done()


def compose_can(c, lf):
    # rot=180 (not the datasheet-default 0): U2's CANH/CANL (pins 6/7) are
    # drawn on the symbol's RIGHT side and TXD/RXD (pins 1/4) on the LEFT at
    # rot=0 -- backwards for this sheet's actual flow (FL1/the RJ-45 side
    # sits to U2's LEFT, the CAN_TX/CAN_RX io exports sit to U2's RIGHT).
    # At rot=0 that forced the CANH/CANL wires to wrap ALL THE WAY AROUND
    # U2's own body to reach the far-side pins (measured: 2 wire_through_body
    # hits, the horizontal run from FL1's side punching straight through the
    # SOIC body to land on the pin drawn on the opposite face). rot=180 swaps
    # both axes (a symmetric-about-center body has the same bbox either way),
    # putting CANH/CANL on the LEFT (facing FL1, short direct hop) and
    # TXD/RXD on the RIGHT (facing the io exports, if anything shorter than
    # before) -- the existing TXD/RXD block below queries pins dynamically
    # via c.pin(), so it repositions for free with no code change there.
    c.place("U2", 45, 40, 180)
    # U2.3 (VCC) and C4.1 (its bypass) are left UNCONSUMED and un-wired --
    # +5VSB_RJ is the GLOBAL bus (see 03-hub-link's note), each pin gets its
    # own global_label stub rather than a custom-routed local connection.
    # U2.5 (VIO) and C5.1 (its bypass) are BOTH members of the +3V3
    # POWER_PORTS net -- SAME treatment (measured bug, fixed: an earlier
    # version drew an explicit wire between them and consumed both ends,
    # which suppresses the automatic per-pin +3V3 power-flag stamp on
    # BOTH sides at once, leaving the pair joined to each other but not to
    # the actual +3.3V rail -- ERC correctly reported U2 pin 5 as
    # unconnected/not-driven). Leaving both fully alone lets the generic
    # pass stamp its own "+3V3" flag at each independently; they still land
    # on the same net by name, no local wire needed (identical to how
    # every other bare power-net pin in this file is handled).
    c.place("C4", 70, 20)
    c.place("C5", 70, 60)

    c.place("FL1", 15, 70)
    # R6/R7 rotated 90 (a HORIZONTAL 2-pin, pitch 4u) and relocated to sit
    # directly ABOVE / BELOW FL1's own body, spanning between its two same-
    # side pins -- see the long comment below for why this replaced the
    # original far-away (X=15/35, Y=90) placement.
    c.place("R6", 15, 66, 90)
    c.place("R7", 15, 74, 90)
    fl1, fl2, fl3, fl4 = (c.pin("FL1", "1"), c.pin("FL1", "2"),
                          c.pin("FL1", "3"), c.pin("FL1", "4"))
    r6a, r6b = c.pin("R6", "1"), c.pin("R6", "2")
    r7a, r7b = c.pin("R7", "1"), c.pin("R7", "2")
    u2_7, u2_6 = c.pin("U2", "7"), c.pin("U2", "6")
    # CAN_H: FL1.1 (RJ side) -bypass R6- FL1.3 (xcvr side) -> U2.7
    # CAN_L: FL1.2 (RJ side) -bypass R7- FL1.4 (xcvr side) -> U2.6
    #
    # FL1's own 4 pins are the hazard: 1/2 sit at X=10 only 2u apart in Y
    # (69/71), and 3/4 the same at X=20 -- so a bypass wire leaving pin 1 and
    # travelling more than 2u down the SAME X=10 column runs straight
    # through pin 2's own location (a measured near-miss: KiCad connects a
    # wire to ANY pin it transits, not just a declared endpoint, so this
    # would have silently tied CAN_H to CAN_L at FL1.2). Two earlier
    # attempts (a shared vertical-then-horizontal jog, then a horizontal-
    # first jog routing R6/R7 far below at Y=90) each cleared one hazard
    # while re-hitting FL1's body, R6/R7's own bodies, or this pin-transit
    # case. FIXED by placing R6/R7 where a real choke bypass belongs -- in
    # the narrow gap directly above (pins 1/3, the Y=69 row) and below
    # (pins 2/4, the Y=71 row) FL1's own body (Y=[68,72]) -- so the bypass
    # loop never needs to travel past the OTHER row's pin at all:
    #   CAN_H (upper row): fl1 up to y=66 (clear of the body, short of fl2's
    #     y=71) -> right to R6.1(13,66) -> R6 -> R6.2(17,66) -> right to
    #     x=20 -> down to fl3(20,69) closes the loop; fl3 also fans a
    #     SEPARATE tap straight up-then-right to U2.7 (35,42 after the
    #     rot=180 above), never revisiting R6's position.
    #   CAN_L (lower row): fl2 down to y=74 (clear of the body, past fl1's
    #     y=69) -> right to R7.1(13,74) -> R7 -> R7.2(17,74) -> right to
    #     x=20 -> up to fl4(20,71); fl4 fans its own tap, nudged to x=21
    #     first (FL1's pins 3/4 share x=20, so this keeps CAN_L's long-leg
    #     column off CAN_H's) -> up to y=38 -> right to U2.6(35,38).
    # Verified (script, not just by hand): every segment stays outside both
    # bodies' (shrunk) boxes, and the only CAN_H/CAN_L segment intersection
    # left is one interior-interior crossing (neither wire has a vertex
    # there) -- the ordinary, connection-free "wires cross on the page"
    # case, not the dangerous endpoint-on-interior one.
    c.wire(fl1, (fl1[0], 66), (r6a[0], 66), r6a)
    c.use(("FL1", "1"), ("R6", "1"))
    c.io("CAN_H_RJ", "left", from_pt=(fl1[0], fl1[1]))
    c.wire(r6b, (fl3[0], r6b[1]), fl3)
    c.wire(fl3, (fl3[0], u2_7[1]), u2_7)
    c.use(("FL1", "3"), ("R6", "2"), ("U2", "7"))
    c.wire(fl2, (fl2[0], 74), (r7a[0], 74), r7a)
    c.use(("FL1", "2"), ("R7", "1"))
    c.io("CAN_L_RJ", "left", from_pt=(fl2[0], fl2[1]))
    c.wire(r7b, (fl4[0], r7b[1]), fl4)
    c.use(("FL1", "4"), ("R7", "2"))
    nudge4 = (fl4[0] + 1, fl4[1])
    c.wire(fl4, nudge4, (nudge4[0], u2_6[1]), u2_6)
    c.use(("U2", "6"))

    # U2 pins 1 (TXD/CAN_TX) and 4 (RXD/CAN_RX) exit on U2's LEFT side (local
    # x=-12.7mm) but both sit at a Y inside U2's own body Y-range (absolute
    # [34,46]), so routing straight "right" from them cuts through U2's body.
    # Jog straight up first (X stays at the pin's own X, which is left of the
    # body's left edge, so the vertical leg never crosses the body), THEN
    # head right from a Y clear of the body.
    u2_1, u2_4 = c.pin("U2", "1"), c.pin("U2", "4")
    tx_y, rx_y = 10, 14
    c.wire(u2_1, (u2_1[0], tx_y))
    c.wire(u2_4, (u2_4[0], rx_y))
    c.use(("U2", "1"), ("U2", "4"))
    c.io("CAN_TX", "right", from_pt=(u2_1[0], tx_y))
    c.io("CAN_RX", "right", from_pt=(u2_4[0], rx_y))
    # single-line was measured OFF-SHEET (cec_sch_gates --sheet-bounds: this
    # leaf's own text is long enough that, added to its page position, it ran
    # past the A4 297mm right edge). An embedded "\n" does NOT fix it --
    # cec_sch_layout._unescape (shared, out of this task's scope to edit)
    # only unescapes \" and \\, not \n, so the off-sheet checker's width
    # computation still sees the literal two-char "\n" as part of one long
    # line (measured: still flagged after adding it). Two SEPARATE caption
    # calls, stacked, sidesteps that gap entirely (each is its own text
    # object, no embedded-newline decoding involved).
    c.caption("TJA1051T/3, classical 500k, no module termination;", 10, 4)
    c.caption("FL1 CAN CMC position DNP with the H3a-PATTERN 0R bypasses "
              "R6/R7 (spec Sec 3.1/7.5)", 10, 7)
    c.done()


def compose_usb_flash(c, lf):
    c.place("D6", 15, 45)   # USBLC6-2SC6 leftmost (its own left pins carry
                            # the USB_D_P/N hier anchors -- eps precedent)
    c.place("J3", 70, 45)
    c.place("D5", 100, 20)
    c.place("FB2", 100, 45)
    c.place("C10", 130, 45)
    c.place("R18", 130, 20)
    c.place("R19", 130, 70)

    j_vbus = c.pin("J3", "A4")
    d5_1, fb2_1 = c.pin("D5", "1"), c.pin("FB2", "1")
    # J3 (a USB-C receptacle) draws EVERY signal pin (A4-A9,B4-B9) on its
    # OWN right edge (one column, u_x=82, ~2u pitch) -- so a wire leaving
    # any one of them that travels vertically along that SAME column
    # before diverging passes straight through every OTHER pin on it
    # (measured the hard way: KiCad connects a wire to any pin it
    # transits, not just a declared endpoint -- the ORIGINAL single-jog
    # wiring here, e.g. `c.wire(j_vbus, (j_vbus[0], fb2_1[1]), fb2_1)`,
    # merged VBUS/CC1/CC2/D+/D- into ONE node -- exported netlist showed
    # `Net-(D5-K)` containing J3.A4/A5/A6/A7/A9/B4/B5/B6/B7/B9, D5.1,
    # D6.4/5/6, FB2.1, R18.1 and R19.1 all together). Separately, three of
    # these same wires crossed straight through J3's own drawn body (u
    # X=[62,78] Y=[31,59]) -- audit-sch.py's wire_through_body. FIXED:
    # every J3 pin needing a wire gets (a) its OWN escape nudge immediately
    # off X=82 so its onward vertical leg never shares the shared column,
    # and (b) where the destination is on the FAR side of the body (D6, at
    # u_x~15-19), a detour to a Y clear of the body's own Y-span before
    # crossing back through its X-range.
    vbus_rx = j_vbus[0] + 2
    c.wire(j_vbus, (vbus_rx, j_vbus[1]))
    c.wire((vbus_rx, j_vbus[1]), (vbus_rx, d5_1[1]), d5_1)
    c.wire((vbus_rx, j_vbus[1]), (vbus_rx, fb2_1[1]), fb2_1)
    c.use(("J3", "A4"), ("D5", "1"), ("FB2", "1"))
    # A9/B4/B9 are DRAWN at the exact same symbol-local point as A4 (measured:
    # all four = local (15.24,15.24,180)) -- real coincident-pin points are
    # electrically joined by KiCad connectivity with no wire needed, so
    # marking them consumed (no separate label) is correct, not a bug.
    c.use(("J3", "A9"), ("J3", "B4"), ("J3", "B9"))   # coincident VBUS pins

    # D6 (USBLC6-2SC6) pin 5 = VBUS_RAW -- NOT coincident with J3.A4 (a
    # different local point on a different part), so it needs an explicit
    # tie into the same VBUS_RAW node (measured bug, fixed: leaving it
    # unconsumed let the generic pass auto-label it independently at D6's
    # own position, which is exactly the kind of coincidental-row collision
    # that merged unrelated nets in 02-sense -- see that leaf's note). This
    # leg crosses to the OPPOSITE (left) side of J3's body from the VBUS
    # fan above, so it gets its own nudge (distinct X, away from vbus_rx)
    # and detours ABOVE the body's Y-span (u Y<31) -- a different band
    # from D+/D-'s below-body detours further down, so none of the three
    # cross-body legs can run collinear with each other.
    d6_5 = c.pin("D6", "5")
    vbus_lx, above_y = j_vbus[0] - 1, 26
    d6_5x = d6_5[0] + 3   # clear of D6's own body (u X=[13,17])
    c.wire(j_vbus, (vbus_lx, j_vbus[1]), (vbus_lx, above_y),
           (d6_5x, above_y), (d6_5x, d6_5[1]), d6_5)
    c.use(("D6", "5"))

    fb2_2, c10_1 = c.pin("FB2", "2"), c.pin("C10", "1")
    c.wire(fb2_2, (c10_1[0], fb2_2[1]), c10_1)
    c.use(("FB2", "2"), ("C10", "1"))
    c.io("VBUS", "right", from_pt=(fb2_2[0], fb2_2[1]))

    d6_1, d6_3 = c.pin("D6", "1"), c.pin("D6", "3")
    c.io("USB_D_P", "left", from_pt=(d6_1[0], d6_1[1]))
    c.io("USB_D_N", "left", from_pt=(d6_3[0], d6_3[1]))
    c.use(("D6", "1"), ("D6", "3"))

    # D6 pins 6/4 are the SAME USB_D_P/USB_D_N nets' OTHER leg (the
    # USBLC6-2SC6 clamps between the two), and J3's A6/B6 (D+) and A7/B7
    # (D-) are the USB-C connector's flip-orientation-redundant pairs --
    # NONE of these six points are naturally coincident with each other or
    # with D6's pin1/pin3 anchors (each is its own distinct symbol-local
    # point), so every one needs an explicit tie; this was the other half
    # of the same measured merge bug (all six left to the generic pass).
    # The A6-B6 and A7-B7 internal ties below stay as-is (their own short
    # jog column, u_x+10/+14, never revisits the shared J3 column or any
    # body) -- only the onward D6-bound legs needed fixing.
    d6_6, d6_4 = c.pin("D6", "6"), c.pin("D6", "4")
    j3_a6, j3_b6 = c.pin("J3", "A6"), c.pin("J3", "B6")
    j3_a7, j3_b7 = c.pin("J3", "A7"), c.pin("J3", "B7")
    c.wire(j3_a6, (j3_a6[0] + 10, j3_a6[1]), (j3_a6[0] + 10, j3_b6[1]), j3_b6)
    c.use(("J3", "A6"), ("J3", "B6"))
    c.wire(j3_a7, (j3_a7[0] + 14, j3_a7[1]), (j3_a7[0] + 14, j3_b7[1]), j3_b7)
    c.use(("J3", "A7"), ("J3", "B7"))
    # D+ (a6) and D- (a7) both cross to D6's FAR side, and d6_6/d6_4 sit
    # only 2u apart at D6's own u_x=19 -- the SAME two-pins-close-together
    # hazard as FL1 in 04-can (see that leaf's note), so each gets its own
    # nudge X, its own below-body detour Y (distinct from each other AND
    # from d6_5's above-body detour), and its own D6-side approach column
    # (distinct from the OTHER pin's target, 2u away at the same X).
    dplus_nx, dplus_y, dplus_ax = j3_a6[0] - 3, 67, d6_6[0] + 4
    c.wire(j3_a6, (dplus_nx, j3_a6[1]), (dplus_nx, dplus_y),
           (dplus_ax, dplus_y), (dplus_ax, d6_6[1]), d6_6)
    c.use(("D6", "6"))
    dminus_nx, dminus_y, dminus_ax = j3_a7[0] - 2, 64, d6_4[0] + 2
    c.wire(j3_a7, (dminus_nx, j3_a7[1]), (dminus_nx, dminus_y),
           (dminus_ax, dminus_y), (dminus_ax, d6_4[1]), d6_4)
    c.use(("D6", "4"))

    cc1, cc2 = c.pin("J3", "A5"), c.pin("J3", "B5")
    r18_1, r19_1 = c.pin("R18", "1"), c.pin("R19", "1")
    cc1_rx, cc2_rx = cc1[0] + 3, cc2[0] + 4
    c.wire(cc1, (cc1_rx, cc1[1]), (cc1_rx, r18_1[1]), r18_1)
    c.wire(cc2, (cc2_rx, cc2[1]), (cc2_rx, r19_1[1]), r19_1)
    c.use(("J3", "A5"), ("J3", "B5"), ("R18", "1"), ("R19", "1"))

    # B1/A12/B12 are likewise drawn coincident with A1 (measured: all four =
    # local (0.0,-22.86,90)) -- same coincident-point reasoning as the VBUS
    # quad above; A1 itself is left to the GND powerflag/POWER_PORTS pass.
    c.use(("J3", "B1"), ("J3", "A12"), ("J3", "B12"))  # coincident GND pins

    c.caption("USB-C 2.0 flash/debug + H3 standalone-mode USB ESD/EMC suite "
              "(spec Sec 6.14/7.5)", 4, 6)
    c.note("VBUS ORs into +5V_LOGIC_OR through D4 (SS34) in 05-mcu; USB is a "
           "DATA path + bench-flash power only, never the LED power feed", 4, 90)
    c.done()


def compose_mcu(c, lf):
    c.place("U1", 90, 100)
    _grid_place(c, ["C6", "C7", "C39"], 30, 200, 3, dx=16)
    c.place("R8", 130, 200)
    c.place("SW2", 130, 216)
    c.place("R9", 150, 200)
    c.place("SW1", 150, 216)

    en, gpio0 = c.pin("U1", "45"), c.pin("U1", "4")
    # Both EN(45) and GPIO0(4) exit U1 on its LEFT side (pin_out dx<0), so
    # BOTH pull-up hangs must run LEFTWARD (measured bug, fixed: EN's run
    # originally went RIGHTWARD toward SW2 -- SW2 happens to sit to the
    # right, below U1 -- which drove it straight across U1's own body;
    # audit-sch.py's wire_through_body caught it). Fixed the same way
    # GPIO0/SW1 already does it correctly below: go left past the body
    # first, then down and back right at SW2's own row (Y=216, well below
    # U1, so the return leg never re-crosses it). EN's column (-44/-34) is
    # offset 4u from GPIO0's (-40/-30) -- EN(Y=80) and GPIO0(Y=84) are only
    # 4u apart, so sharing one column would run both pull-ups' vertical
    # descents collinear/overlapping over their whole shared span (the
    # same class of hazard the 04-can FL1 fix hit) -- separate columns keep
    # them apart no matter how far down they both travel.
    arch.pullup_hang(c, en, en[0] - 44, "R8", rx=en[0] - 34, rail_pin="1", above=True)
    c.use(("U1", "45"))
    sw2a = c.pin("SW2", "1")
    c.wire((en[0] - 44, en[1]), (en[0] - 44, sw2a[1]), sw2a)
    c.use(("SW2", "1"))
    arch.pullup_hang(c, gpio0, gpio0[0] - 40, "R9", rx=gpio0[0] - 30, rail_pin="1", above=True)
    c.use(("U1", "4"))
    sw1a = c.pin("SW1", "1")
    c.wire((gpio0[0] - 40, gpio0[1]), (gpio0[0] - 40, sw1a[1]), sw1a)
    c.use(("SW1", "1"))

    # logic-power diode-OR: D2(+5V_LED) / D3(+5VSB_RJ) / D4(VBUS) -> U3.IN
    c.place("D2", 20, 40, 270)
    c.place("D3", 20, 60, 270)
    c.place("D4", 20, 80, 270)
    c.place("U3", 50, 60)
    d2k, d2a = c.pin("D2", "1"), c.pin("D2", "2")
    d3k, d3a = c.pin("D3", "1"), c.pin("D3", "2")
    d4k, d4a = c.pin("D4", "1"), c.pin("D4", "2")
    u3in = c.pin("U3", "1")
    orx = u3in[0] - 10
    c.wire(d2k, (orx, d2k[1]))
    c.wire(d3k, (orx, d3k[1]))
    c.wire(d4k, (orx, d4k[1]))
    c.wire((orx, d2k[1]), (orx, d4k[1]))
    c.wire((orx, d3k[1]), (orx, u3in[1]), u3in)
    u3en = c.pin("U3", "3")
    c.wire(u3in, (u3in[0], u3en[1]))   # EN strapped to IN -- always-on LDO
    c.use(("D2", "1"), ("D3", "1"), ("D4", "1"), ("U3", "1"), ("U3", "3"))
    # +5V_LOGIC_OR has no genuine "power_out" driver anywhere on this
    # purely-local, single-sheet net (D2/D3/D4 cathodes are diode/passive
    # pins, C8 is passive) -- ERC's power_pin_not_driven fires on U3.1 (the
    # LDO's own "Power input"-typed IN pin). A PWR_FLAG stamped exactly at
    # u3in's OWN already-wired point marks it externally driven directly on
    # the real node (measured bug, fixed: the previous approach used
    # L05.powerflag_nets, whose "else" branch draws a PLAIN LOCAL LABEL in
    # a separate self-contained anchor block -- that label text never
    # actually touches the real +5V_LOGIC_OR wiring, which carries no label
    # of its own anywhere, so the anchor's tiny 2-point label+flag circuit
    # stayed electrically disconnected from the real diode-OR node despite
    # sharing the same net NAME in this script's own Python model; ERC
    # still reported U3.1 undriven). Stamping directly on a real, already-
    # wired coordinate is the same proven technique used for +5V_LED and
    # +5VSB_RJ's anchors.
    c.stamp("PWR_FLAG", u3in[0], u3in[1], 0)
    # D2's anode (+5V_LED) and D3's anode (+5VSB_RJ) are left UNCONSUMED and
    # un-wired: both are GLOBAL buses now (+5V_LED touches 02/05/06/08;
    # +5VSB_RJ touches 03/04/05 -- see 02-sense's identical note), so each
    # gets its own independent global_label stub from the generic pass.
    # D4's anode (VBUS) IS this leaf's own hier_exports anchor for that
    # ordinary 2-leaf pair (07-usb-flash <-> 05-mcu), so it still routes
    # through the S1 edge column.
    c.io("VBUS", "left", from_pt=(d4a[0], d4a[1]))
    c.use(("D4", "2"))

    c.place("C8", 66, 50)
    c8_1 = c.pin("C8", "1")
    c.wire(u3in, (u3in[0], 50), (c8_1[0], 50), c8_1)
    c.use(("C8", "1"))
    # U3.5 (OUT) and C9.1 (its bulk cap) are BOTH members of the +3V3
    # POWER_PORTS net -- leave them UNCONSUMED and un-wired (measured bug,
    # fixed: consuming both ends of a manual wire suppresses the automatic
    # per-pin power-flag stamp on BOTH sides -- build_leaf's generic pass
    # skips any pin in `consumed` outright, so neither end ever got a real
    # "+3V3" power symbol; the LDO output was electrically joined to its own
    # bypass cap but disconnected from the actual 3.3V rail -- ERC correctly
    # reported U3 pin 5 as unconnected). Each gets its own independent +3V3
    # flag from the generic pass and they still land on the same net by name.
    c.place("C9", 66, 70)

    for net in ("CAN_TX", "CAN_RX", "DETECT_SENSE", "ISENSE_TOTAL",
                "VRAIL_5V_DIV", "USB_D_P", "USB_D_N",
                "LED1_DATA", "LED2_DATA", "LED3_DATA", "LED4_DATA",
                "LED5_DATA", "LED6_DATA", "LED7_DATA", "LED8_DATA",
                "STATUS_LED_DATA"):
        ref, pin = lf.hier_exports[net][1]
        _pt, (dx, _dy) = c.pin_out(ref, pin)
        c.io(net, "left" if dx < 0 else "right")

    c.caption("ESP32-S3-MINI-1-N4R2 (OQ-29 working basis) + BOOT/RESET + "
              "3-way logic-power OR + LP5907 3V3 LDO", 20, 8)
    c.note("D2/D3/D4 = SS34 ORing diodes (SATA/RJ-45-5VSB/USB); +5VSB_RJ leg "
           "is a PROPOSAL (README.md Sec 3); GPIO map is a working basis "
           "(README.md Sec 1)", 20, 240)
    c.done()


def compose_led_outputs(c, lf):
    # 74AHCT244 group1 (ch1-4): input pins on U5's LEFT, output on the RIGHT.
    # group2 (ch5-8): MIRRORED -- input on the RIGHT, output on the LEFT.
    # Build each channel's downstream chain (R -> BAT54S -> PESD -> header)
    # extending AWAY from U5 in whichever direction that channel's own output
    # pin actually points (sgn, computed from the real pin geometry -- never
    # assumed), so group2's channels correctly mirror group1's instead of
    # colliding back through the IC body.
    c.place("U5", 130, 220)
    G_ = cec_sch.GRID
    y = 20
    for ch in range(1, 9):
        in_pin, out_pin = _AHCT244_CH[ch]
        _o_pt, (odx, _ody) = c.pin_out("U5", out_pin)
        sgn = 1 if odx > 0 else -1
        r, dclamp, dtvs, j = f"R{9+ch}", f"D{6+ch}", f"D{14+ch}", f"J{3+ch}"
        rx = _o_pt[0] + sgn * 16

        c.place(r, rx, y, 90)
        opin = c.pin("U5", out_pin)
        # R (rot90) has pin1 on its own LEFT, pin2 on its own RIGHT. Group1
        # (sgn=+1) extends the downstream chain RIGHTWARD, so pin2 (the
        # right-side pin) is the natural downstream connection; group2
        # (sgn=-1, mirrored) extends LEFTWARD, so pin1 becomes the natural
        # downstream side instead -- pick the upstream/downstream PIN NUMBER
        # per sgn rather than hardcoding 1=upstream/2=downstream (measured
        # bug, fixed: the hardcoded version put the downstream pin on the
        # side AWAY from the downstream chain for the whole mirrored group,
        # so the r2->dclamp wire had to cross back through R's own body to
        # reach it -- audit-sch.py's wire_through_body caught it on R14-R17).
        r_up, r_dn = ("1", "2") if sgn > 0 else ("2", "1")
        r1 = c.pin(r, r_up)
        c.wire(opin, (r1[0], opin[1]), r1)
        c.use(("U5", out_pin), (r, r_up))

        r2 = c.pin(r, r_dn)
        c.place(dclamp, rx + sgn * 16, y - 6, 270)
        c.place(dtvs, rx + sgn * 26, y, 270)
        c.place(j, rx + sgn * 44, y)
        d3 = c.pin(dclamp, "3")
        d1 = c.pin(dtvs, "1")
        jp3 = c.pin(j, "3")
        c.wire(r2, (d3[0], r2[1]), d3)
        c.wire(d3, (d1[0], d3[1]), d1)
        c.wire(d1, (jp3[0], d1[1]), jp3)
        c.use((r, r_dn), (dclamp, "3"), (dtvs, "1"), (j, "3"))

        # dclamp.2 (BAT54S cathode) + j.1 are BOTH +5V_LED GLOBAL members;
        # dtvs.2 (PESD cathode-side) + j.4 are BOTH GND POWER_PORTS members;
        # dclamp.1 (BAT54S anode) is ALSO a bare GND member. ALL FIVE are
        # left UNCONSUMED and un-wired (measured bug, fixed: an earlier
        # version manually wired dclamp.2<->j.1 and dtvs.2<->j.4 and consumed
        # every pin, which suppresses the automatic per-pin stamp on BOTH
        # ends of EACH pair -- neither pair ever reached the real +5V_LED/
        # GND net, each showing up as its own tiny isolated "Net-(...)"
        # island per channel instead of merging into the 9-member +5V_LED
        # bus / 74-member GND net; dclamp.1's own stray stub-to-nowhere was
        # a separate instance of the identical mistake). Leaving all five to
        # the generic pass gives each its own independent global_label/GND
        # flag -- no local copper needed, they merge by name exactly like
        # every other bare power/global pin in this file.

        _i_pt, (idx, _idy) = c.pin_out("U5", in_pin)
        ipin = c.pin("U5", in_pin)
        c.io(f"LED{ch}_DATA", "left" if idx < 0 else "right",
             from_pt=(ipin[0], ipin[1]))
        c.use(("U5", in_pin))
        y += 30

    c.caption("74AHCT244 octal level-shift + 8x (series R, BAT54S clamp, "
              "PESD TVS, ARGB header) -- spec Sec 7.3", 10, 4)
    c.note("BAT54S pin1=anode->GND, pin3=tap->DATA, pin2=cathode->+5V_LED "
           "(verified by rendering the vendored symbol -- see README.md Sec 4); "
           "header pin 2 (key position) left NC, OQ-36", 10, 260)
    c.done()


def compose_status(c, lf):
    c.place("U6", 40, 30)
    c.place("R20", 65, 30, 90)
    c.place("DL1", 90, 30)
    c.place("C11", 40, 10)

    u6a, u6b = c.pin("U6", "1"), c.pin("U6", "2")
    c.wire(u6a, (u6a[0] - 6, u6a[1]))
    c.wire(u6b, (u6a[0] - 6, u6b[1]), (u6a[0] - 6, u6a[1]))
    c.use(("U6", "1"), ("U6", "2"))
    c.io("STATUS_LED_DATA", "left", from_pt=((u6a[0] - 6), u6a[1]))

    u6y, r20a = c.pin("U6", "4"), c.pin("R20", "1")
    c.wire(u6y, (r20a[0], u6y[1]), r20a)
    c.use(("U6", "4"), ("R20", "1"))
    r20b, dl3 = c.pin("R20", "2"), c.pin("DL1", "3")
    c.wire(r20b, (r20b[0], dl3[1]), dl3)
    c.use(("R20", "2"), ("DL1", "3"))

    # U6.5 (VCC) and C11.1 (its bypass) are BOTH members of the +5V_LED
    # GLOBAL bus -- leave them UNCONSUMED and un-wired (same class of bug as
    # 04-can/05-mcu's power-pin fix: consuming both ends of a manual wire
    # suppresses the automatic per-pin stamp -- for a global net that stamp
    # IS the independent global_label each occurrence needs, so wiring +
    # consuming both left this node joined to itself but disconnected from
    # the actual +5V_LED bus). Each gets its own global_label from the
    # generic pass; DL1.4 (the third +5V_LED member) is already handled the
    # same hands-off way.

    c.caption("SK6812MINI status pixel, level-shifted (Hub Standard's own "
              "U6 precedent, verbatim)", 10, -4)
    c.done()


COMPOSERS = {
    "01-power-input": compose_power_input,
    "02-sense": compose_sense,
    "03-hub-link": compose_hub_link,
    "04-can": compose_can,
    "07-usb-flash": compose_usb_flash,
    "05-mcu": compose_mcu,
    "06-led-outputs": compose_led_outputs,
    "08-status": compose_status,
}

# ---------------------------------------------------------------------------
# ROOT (thin parent) geometry. Every leaf gets its OWN Y-band, monotonically
# staggered by RANK (the fully-conservative form of gen-12vhpwr-beta.py's
# Y-staircase discipline): several pairs SKIP over an intermediate leaf's X
# range (e.g. 01-power-input -> 05-mcu skips 02/03/04/07-usb-flash), and a
# skip-ahead lane travels the full X-span at its SOURCE's own row height, so
# giving every leaf a distinct, non-overlapping Y-band means no lane can ever
# reach a foreign leaf's box regardless of which leaves it geometrically
# skips over (see that generator's BOX dict comment for the fully-worked
# rationale -- the same hazard applies here, this board just has MORE
# distinct source leaves feeding into 05-mcu than 12vhpwr-standard did).
#
# X-ORDERING NOTE: build_thin_parent's 2-pin-net check sorts a net's two leaf
# occurrences by ABSOLUTE PAGE X and requires the smaller-X one to be the
# "right"-side stub and the larger-X one the "left"-side stub (i.e. any two
# leaves joined by a direct 2-pin net need non-overlapping X ranges, smaller
# rank strictly left of larger rank -- NOT just distinct Y bands). 02-sense
# (rank 2) has a direct pair with 01-power-input (rank 1, +5V_LED_IN) as well
# as with 05-mcu (rank 6, ISENSE_TOTAL), so its X must clear 01's right edge
# AND stay left of 05's left edge; 04-can (rank 4) similarly must clear
# 03-hub-link's (rank 3) right edge for CAN_H_RJ/CAN_L_RJ while staying left
# of 05. 05-mcu's own X must in turn clear the RIGHTMOST right-edge among
# every leaf that connects directly to it (01/02/03/04/07), and 06/08 must
# clear 05's right edge.
#
# TAP MARGIN NOTE (measured live): with lane_labels=True and no root_exports,
# EVERY net gets the lane_labels "tap" treatment, which backs a local-label
# stub OFF the lane by a further 7.62mm (single-member destination group) or
# 6.35mm (group of 4+, e.g. 05-mcu's 8-member LED_DATA convergence) BEHIND
# the naive source->dest lane column -- i.e. clearance between two directly-
# paired leaves must exceed not just their own edge-to-edge gap but that
# extra backward inset too, or the tap stub backs INTO the source leaf's own
# box (measured: a 6-unit/7.62mm gap between 01-power-input and 02-sense
# put the +5V_LED_IN tap stub's far end AT X=215.9mm, inside 01's own box
# whose right edge is X=220.98mm -- "wire ... crosses sheet box
# 01-power-input"). Fix: every directly-paired leaf gets >=30 GRID UNITS
# (>=38mm) of clearance from its partner's edge, comfortably past the
# largest tap inset (~30mm, worst case: 05-mcu's 8-member LED group at
# k=7); 05-mcu's own left edge clears the rightmost of {01,02,03,04,07} by
# the same margin, and 06/08 clear 05's right edge likewise.
BOX = {
    "01-power-input": (4,   8,   170, 100),
    "02-sense":        (210, 130, 110, 50),
    "03-hub-link":     (4,   200, 110, 60),
    "04-can":          (150, 280, 130, 100),
    "07-usb-flash":    (4,   400, 170, 100),
    "05-mcu":          (360, 8,   190, 260),
    "06-led-outputs":  (600, 8,   260, 300),
    "08-status":       (600, 330, 130, 60),
}
LEAF_PAPER = {
    "01-power-input": "A3", "02-sense": "A4", "03-hub-link": "A4",
    "04-can": "A4", "07-usb-flash": "A4", "05-mcu": "A2",
    "06-led-outputs": "A1", "08-status": "A4",
}
ROOT_PAPER = "A0"

# GND arrays bused to one link (owner directive, round-4 plan doc item 2 --
# applied here too for consistency): U1 (ESP32-S3-MINI-1) carries 21 GND pads.
GND_BUS_TARGETS = {"05-mcu": ["U1"]}

# The two genuine N-way buses on this board (every other named net is a
# clean 2-leaf pair -- verified by the owners-count guard in build() below).
# +5V_LED: produced in 02-sense, consumed in 05-mcu (logic-power OR),
#   06-led-outputs (buffer VCC + all 8 header 5V pins), AND 08-status
#   (status pixel power) -- 4 leaves.
# +5VSB_RJ: produced in 03-hub-link (the RJ-45 5VSB entry bead), consumed in
#   04-can (TJA1051T/3 VCC) AND 05-mcu (the logic-power OR's 3rd leg) --
#   3 leaves.
_5V_LED_LEAVES = {"02-sense", "05-mcu", "06-led-outputs", "08-status"}
_5VSB_RJ_LEAVES = {"03-hub-link", "04-can", "05-mcu"}
GLOBAL_NET_NAMES = {"+5V_LED", "+5VSB_RJ"}
GLOBAL_NETS_PER_LEAF = {}
for _lid in LEAF_ORDER:
    _s = set()
    if _lid in _5V_LED_LEAVES:
        _s.add("+5V_LED")
    if _lid in _5VSB_RJ_LEAVES:
        _s.add("+5VSB_RJ")
    if _s:
        GLOBAL_NETS_PER_LEAF[_lid] = _s


# FL1 (the CAN CMC position) is this board's only DNP part -- the H3a-
# PATTERN (spec Sec 3.1/7.5): the series CMC itself is left unpopulated in
# production, with R6/R7 as the always-populated 0R bypasses carrying the
# real signal path (KiCad would otherwise net a DNP series part as if it
# were connected, per CLAUDE.md). cec_sch_compose.build_leaf has no per-part
# DNP parameter and unconditionally emits `(dnp no)`, so this is a post-write
# patch identical to gen-12vhpwr-beta.py's/gen-module-beta.py's own
# `_patch_dnp` helper (kept OUT of cec_sch_compose.py deliberately, same as
# those two generators) -- without it the exported BOM would show FL1 as a
# normal populated part, contradicting its own Value text ("...DNP") and the
# spec.
DNP_REFS = {"FL1"}


def _patch_dnp(path, dnp_refs):
    """Post-write patch: flip (dnp no) -> (dnp yes) for the given refs."""
    if not dnp_refs:
        return 0
    text = open(path).read()
    n = 0
    out, pos = [], 0
    for m in re.finditer(r'\t\(symbol\n', text):
        if m.start() < pos:
            continue
        blk = cec_sch.carve(text, m.start())
        rm = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', blk)
        if rm and rm.group(1) in dnp_refs and "(dnp no)" in blk:
            out.append(text[pos:m.start()])
            out.append(blk.replace("(dnp no)", "(dnp yes)", 1))
            pos = m.start() + len(blk)
            n += 1
    out.append(text[pos:])
    if n:
        open(path, "w").write("".join(out))
    return n


def build(force=False):
    if os.path.isfile(ROOT_SCH) and not force:
        raise SystemExit(f"{ROOT_SCH} already exists -- refusing to run "
                          f"(pass --force to regenerate anyway)")

    name_pin_nets = {}   # this board has no leaf-internal-forced-export nets
                          # (every named net is either a genuine hier_export
                          # pair, the one global_nets bus, or purely internal)

    stats = {}
    for lid in LEAF_ORDER:
        lf = LEAVES[lid]
        c = C.Compose(lf, LIBS)
        COMPOSERS[lid](c, lf)

        out_path = os.path.join(BOARD_DIR, lf.filename)
        st = C.build_leaf(
            lf.parts, lf.nets, lf.footprints, lf.props, lf.placement, lf.nc_skip,
            POWER_PORTS, lf.powerflag_nets, lf.hier_exports, None,
            LIBS, PROJECT_NAME, path_prefix=f"{ROOT_UUID}/{LEAF_SYM_UUIDS[lid]}",
            sheet_instances_path=LEAF_SYM_UUIDS[lid],
            own_uuid=LEAF_OWN_UUIDS[lid], page=str(LEAF_ORDER.index(lid) + 2),
            out_path=out_path, paper=LEAF_PAPER[lid],
            title=f"CEC ARGB Controller Standard: {lf.sheetname}", comment1=lf.desc,
            pwr_base=100 * (LEAF_ORDER.index(lid) + 1), layout=lf.layout,
            global_nets=GLOBAL_NETS_PER_LEAF.get(lid),
            name_pin_nets=name_pin_nets.get(lid), rev=REV)
        n_moved, still = L.nudge_texts(out_path)
        st["nudged"], st["text_overlaps_left"] = n_moved, still
        dnp_here = DNP_REFS & set(lf.parts)
        st["dnp_patched"] = _patch_dnp(out_path, dnp_here)
        for ref in GND_BUS_TARGETS.get(lid, ()):
            res = G.bus_power_ladder(out_path, ref, "GND")
            st.setdefault("gnd_bus", []).append((ref, res["applied"], res.get("flags_removed", 0)))
        try:
            st["flags_spread"] = len(L.spread_power_flags(out_path) or ())
        except Exception:
            st["flags_spread"] = "n/a"
        try:
            st["flags_deduped"] = len(L.dedupe_power_flags(out_path) or ())
        except Exception:
            st["flags_deduped"] = "n/a"
        try:
            st["labels_flipped"] = len(L.flip_label_collisions(out_path) or ())
        except Exception:
            st["labels_flipped"] = "n/a"
        L.nudge_texts(out_path)
        stats[lid] = st
        print(f"{lf.filename}  " + "  ".join(f"{k}={v}" for k, v in st.items()))

    # ---- root: for every leaf, gather its 2-leaf PAIRED nets (nets that
    # appear in exactly one OTHER leaf's hier_exports too); the two true
    # N-way buses (+5V_LED, +5VSB_RJ) are handled via global_nets above and
    # carry NO sheet pin at all (a real KiCad global_label connects each
    # project-wide).
    net_owners = {}
    for lid in LEAF_ORDER:
        for net in LEAVES[lid].hier_exports:
            if net in GLOBAL_NET_NAMES:
                continue
            net_owners.setdefault(net, []).append(lid)
    pair_sides = {}
    for net, owners in net_owners.items():
        if len(owners) != 2:
            raise SystemExit(f"build: net {net!r} appears in {len(owners)} leaf "
                              f"hier_exports {owners} -- expected exactly 2 "
                              f"(non-global nets must be a clean 2-leaf pair); "
                              f"add it to GLOBAL_NET_NAMES if it is a genuine bus")
        lids = sorted(owners, key=lambda l: RANK[l])
        pair_sides[net] = {lids[0]: "right", lids[1]: "left"}

    u = cec_sch.GRID
    leaves_for_parent = []
    for lid in LEAF_ORDER:
        lf = LEAVES[lid]
        bx, by, bw, bh = BOX[lid]
        pins = []
        for net, sides in pair_sides.items():
            if lid in sides:
                pins.append((net, lf.hier_exports[net][0], sides[lid]))
        leaves_for_parent.append({
            "id": lid, "sym_uuid": LEAF_SYM_UUIDS[lid], "filename": lf.filename,
            "sheetname": lf.sheetname, "page": str(LEAF_ORDER.index(lid) + 2),
            "x": bx * u, "y": by * u, "w": bw * u, "h": bh * u, "pins": pins,
        })

    parent_stats = C.build_thin_parent(
        leaves_for_parent, set(), PROJECT_NAME, ROOT_UUID, None, ROOT_UUID,
        out_path=ROOT_SCH, title="CEC ARGB Controller Standard (8-channel)",
        paper=ROOT_PAPER, global_power_exports=None, libs=LIBS, pwr_base=900,
        lane_labels=True, name_pin_nets=None, rev=REV,
        title_comments=(
            f"Root = thin parent: sheet-symbol fan-out/fan-in only, no "
            f"components. Rev {REV} -- NEW board, no alpha lineage (owner "
            f"directive 2026-07-05, spec Sec 7).",
            "Leaf sheets: " + ", ".join(LEAVES[lid].sheetname for lid in LEAF_ORDER),
            "GND/+3V3 are global power nets (per-leaf symbols); +5V_LED "
            "(4 leaves) and +5VSB_RJ (3 leaves) are genuine N-way buses "
            "(global_label, project-wide); every other crossing is a real "
            "drawn sheet-pin lane carrying its exact net name."))
    print(f"{os.path.basename(ROOT_SCH)} (thin parent)  " +
          "  ".join(f"{k}={v}" for k, v in parent_stats.items()))

    # ---- ERC posture for name-pin stubs (measured, KiCad 10.0.4 -- see
    # gen-module-beta.py's identical comment): this board carries no
    # name_pin_nets today, but the workaround is threaded through in case a
    # future revision adds one, matching every other board's driver.
    import json as _json
    pro_path = os.path.join(BOARD_DIR, f"{PROJECT_NAME}.kicad_pro")
    if os.path.isfile(pro_path):
        with open(pro_path) as fh:
            pro = _json.load(fh)
        sev = pro.setdefault("erc", {}).setdefault("rule_severities", {})
        if sev.get("label_dangling") != "warning":
            sev["label_dangling"] = "warning"
            with open(pro_path, "w") as fh:
                _json.dump(pro, fh, indent=2)
                fh.write("\n")
            print(f"{os.path.basename(pro_path)}: erc.rule_severities."
                  f"label_dangling -> warning")
    return stats, parent_stats


def main(argv=None):
    ap_ = argparse.ArgumentParser(description=__doc__)
    ap_.add_argument("--force", action="store_true",
                      help="regenerate even if the root already exists")
    args = ap_.parse_args(argv)
    build(force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
