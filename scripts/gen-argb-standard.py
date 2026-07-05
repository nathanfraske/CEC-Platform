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
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF4702TCE", "LCSC": "C25900"})
ap(L01, "R3", "cec-vendor", "R_Small", "10k", "cec-Resistor_SMD:R_0402_1005Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF1002TCE", "LCSC": "C25744"})
ap(L01, "C1", "cec-vendor", "C_Small", "100u", "cec-Capacitor_SMD:C_1210_3225Metric",
   {"Manufacturer": "Samsung", "MPN": "CL32A107MQVNNNE", "LCSC": "C96446",
    "Description": "+5V_LED bulk cap, charged (slew-limited) through RT1"})
ap(L01, "C2", "cec-vendor", "C_Small", "1n", "cec-Capacitor_SMD:C_0402_1005Metric",
   {"Manufacturer": "Murata", "MPN": "GRM1555C1H102JA01D", "LCSC": "C76947",
    "Description": "Rail-divider ADC filter cap (matches the 12VHPWR VRAIL_DIV precedent)"})

L01.net("SATA_5V_RAW", ("J1", "7"), ("J1", "8"), ("J1", "9"), ("Q1", "1"), ("Q1", "2"), ("Q1", "3"))
L01.net("GND", ("J1", "4"), ("J1", "5"), ("J1", "6"), ("J1", "10"), ("J1", "11"), ("J1", "12"),
        ("R1", "2"), ("C1", "2"), ("R3", "2"), ("C2", "2"))
L01.net("5V_POST_FET", ("Q1", "5"), ("Q1", "6"), ("Q1", "7"), ("Q1", "8"), ("F1", "1"))
L01.net("5V_POST_FUSE", ("F1", "2"), ("RT1", "1"))
L01.net("+5V_LED_IN", ("RT1", "2"), ("C1", "1"), ("R2", "1"))
L01.net("GATE_Q1", ("Q1", "4"), ("R1", "1"))
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
    "+5V_LED_IN":    ("output", ("RS1", "1")),
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
    "+5VSB_RJ":      ("output", ("FB1", "2")),
}
L03.powerflag_nets = ["GND"]


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
    "+5VSB_RJ":  ("output", ("U2", "3")),
}


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
L07.powerflag_nets = ["GND"]


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
ap(L05, "U3", "cec-vendor", "LP5907MFX-3.3", "LP5907MFX-3.3",
   "cec-Package_TO_SOT_SMD:SOT-23-5",
   {"Manufacturer": "Texas Instruments", "MPN": "LP5907MFX-3.3", "LCSC": "C80670"})
ap(L05, "C6", "cec-vendor", "C_Small", "10u", "cec-Capacitor_SMD:C_0805_2012Metric",
   {"Manufacturer": "Samsung", "MPN": "CL21A106KAYNNNE", "LCSC": "C15850"})
ap(L05, "C7", "cec-vendor", "C_Small", "1u", "cec-Capacitor_SMD:C_0603_1608Metric",
   {"Manufacturer": "Samsung", "MPN": "CL10B105KA8NNNC", "LCSC": "C15849"})
ap(L05, "C39", "cec-vendor", "C_Small", "100n", "cec-Capacitor_SMD:C_0402_1005Metric",
   {"Manufacturer": "Samsung", "MPN": "CL05B104KO5NNNC", "LCSC": "C1525"})
ap(L05, "C8", "cec-vendor", "C_Small", "1u", "cec-Capacitor_SMD:C_0603_1608Metric",
   {"Manufacturer": "Samsung", "MPN": "CL10B105KA8NNNC", "LCSC": "C15849",
    "Description": "LDO IN bulk"})
ap(L05, "C9", "cec-vendor", "C_Small", "1u", "cec-Capacitor_SMD:C_0603_1608Metric",
   {"Manufacturer": "Samsung", "MPN": "CL10B105KA8NNNC", "LCSC": "C15849",
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
L05.net("+5V_LOGIC_OR", ("D2", "1"), ("D3", "1"), ("D4", "1"), ("U3", "1"), ("C8", "1"))
L05.net("+3V3", ("U3", "5"), ("C9", "1"), ("C6", "1"), ("C7", "1"), ("C39", "1"),
        ("R8", "1"), ("R9", "1"), ("U1", "3"))
L05.net("GND", ("U3", "2"), ("C6", "2"), ("C7", "2"), ("C39", "2"), ("C8", "2"), ("C9", "2"),
        ("SW1", "1"), ("SW2", "1"),
        ("U1", "1"), ("U1", "2"), ("U1", "42"), ("U1", "43"), ("U1", "46"),
        *[("U1", str(n)) for n in range(47, 66)])
L05.net("EN", ("U1", "45"), ("R8", "2"), ("SW2", "2"))
L05.net("GPIO0", ("U1", "4"), ("R9", "2"), ("SW1", "2"))
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
    "+5V_LED":        ("output", ("D2", "2")),
    "+5VSB_RJ":        ("output", ("D3", "2")),
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
L05.powerflag_nets = ["+5V_LOGIC_OR"]
# +5V_LOGIC_OR has no genuine power_out driver (fed only by 3 diode cathodes,
# all "passive"-typed pins) -- the PWR_FLAG anchor block satisfies ERC's
# power_pin_not_driven on U3.IN, exactly like every diode-ORed rail elsewhere
# in this repo (e.g. ent-common's +5VSB_FUSED after its eFuse).


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

    ap(L06, _r, "cec-vendor", "R_Small", "330",
       "cec-Resistor_SMD:R_0402_1005Metric",
       {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF3300TCE", "LCSC": "C25131",
        "Description": f"LED channel {_ch} series resistor"})
    ap(L06, _dclamp, "cec-vendor", "BAT54S", "BAT54S",
       "cec-Package_TO_SOT_SMD:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-TL",
       {"Manufacturer": "UMW", "MPN": "BAT54S", "LCSC": "C545549",
        "Description": f"LED channel {_ch} DATA-first hot-plug clamp (dual-series "
                       "Schottky, pin1=anode/pin3=tap/pin2=cathode -- VERIFIED by "
                       "rendering the vendored symbol, see README.md Sec 4. Spec "
                       "names \"BAT54W\", which is not a real dual-diode part under "
                       "that name; BAT54S is the verified series-diode part that "
                       "implements the described clamp)"})
    ap(L06, _dtvs, "cec-vendor", "D_Schottky", "PESD5V0S1BA",
       "cec-Diode_SMD:D_SOD-323",
       {"Manufacturer": "Nexperia", "MPN": "PESD5V0S1BA", "LCSC": "C5261083",
        "Description": f"LED channel {_ch} per-line ESD TVS"})
    ap(L06, _j, "cec-vendor", "Header-Male-2.54_1x4", "ARGB_5V_3PIN",
       "cec-Connector_PinHeader_2.54mm:HDR-TH_4P-P2.54-V-M",
       {"Manufacturer": "Ckmtw", "MPN": "B-2100S04P-A110", "LCSC": "C124378",
        "Description": f"LED channel {_ch} ARGB strip header -- plain 1x4 2.54mm, "
                       "pin 2 left NC (real keyed 4-pos/3-used ARGB part does not "
                       "exist on LCSC; OQ-36, see README.md)"})

    # buffer input (from 05-mcu, hier_export, SAME name as that leaf's own
    # export so build_thin_parent pairs the two as one 2-leaf lane)
    L06.net(f"LED{_ch}_DATA", ("U5", _in_pin))
    _hier_exports_06[f"LED{_ch}_DATA"] = ("output", ("U5", _in_pin))
    # buffer output (5V level), leaf-internal only
    L06.net(f"LED{_ch}_BUF", ("U5", _out_pin), (_r, "1"))
    # post-series-resistor node: BAT54S tap (pin3) + PESD anode-side (pin1,
    # signal) + header DATA pin, leaf-internal only
    L06.net(f"LED{_ch}_HDR", (_r, "2"), (_dclamp, "3"), (_dtvs, "1"), (_j, "3"))

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
   {"Manufacturer": "Texas Instruments", "MPN": "SN74AHCT1G08DBVR", "LCSC": "C7526",
    "Description": "2-input AND, both inputs tied = non-inverting 3.3V->5V "
                   "level shift for the SK6812 DIN (Hub Standard's own U6 "
                   "precedent, verbatim)"})
ap(L08, "DL1", "cec-vendor", "SK6812MINI", "SK6812MINI",
   "cec-LED_SMD:LED_SK6812MINI_PLCC4_3.5x3.5mm_P1.75mm",
   {"Manufacturer": "Opsco", "MPN": "SK6812MINI-E", "LCSC": "C2841455",
    "Description": "Status pixel, platform LED language"})
ap(L08, "R20", "cec-vendor", "R_Small", "330", "cec-Resistor_SMD:R_0402_1005Metric",
   {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF3300TCE", "LCSC": "C25131"})
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
    c.wire((busx, p7[1]), (busx, p9[1]))
    c.use(("J1", "7"), ("J1", "8"), ("J1", "9"))

    c.place("Q1", 50, 50, 90)
    q1, q2, q3 = c.pin("Q1", "1"), c.pin("Q1", "2"), c.pin("Q1", "3")
    c.wire((busx, p8[1]), (busx, q2[1]), (q1[0] - 6, q2[1]))
    c.wire((q1[0] - 6, q2[1]), (q1[0] - 6, q1[1]), q1)
    c.wire((q1[0] - 6, q2[1]), q2)
    c.wire((q1[0] - 6, q2[1]), (q1[0] - 6, q3[1]), q3)
    c.use(("Q1", "1"), ("Q1", "2"), ("Q1", "3"))
    q5, q6, q7, q8 = (c.pin("Q1", "5"), c.pin("Q1", "6"),
                      c.pin("Q1", "7"), c.pin("Q1", "8"))
    dbusx = q5[0] + 8
    for p in (q5, q6, q7, q8):
        c.wire(p, (dbusx, p[1]))
    c.wire((dbusx, q7[1]), (dbusx, q6[1]))
    c.wire((dbusx, q6[1]), (dbusx, q5[1]))
    c.use(("Q1", "5"), ("Q1", "6"), ("Q1", "7"), ("Q1", "8"))
    qg = c.pin("Q1", "4")
    c.place("R1", qg[0], qg[1] + 12)
    c.wire(qg, (qg[0], qg[1] + 10))
    c.use(("Q1", "4"), ("R1", "1"))

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
    c.io("+5V_LED_IN", "right", from_pt=(tx / G_, exit_y / G_))

    c.place("C1", tx / G_, 70)
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
    # taps); +5V_LED_IN's anchor pin (RS1.1) still gets the S1 edge-column
    # treatment, but the REST of this leaf's nets (+5V_LED_IN's other member
    # U4.3, and every member of the +5V_LED GLOBAL bus: RS1.2/U4.4/U4.5/C3.1)
    # are left to the generic per-pin pass -- a plain same-name local label
    # (for the hier_export's non-anchor member) or an independent global_label
    # stub (for each +5V_LED pin) is the correct, simplest realization; a
    # global net has NO custom-placement hook (see 05-mcu/06-led-outputs for
    # the same pattern) so hand-wiring it would only fight the mechanism.
    c.place("RS1", 30, 30, 90)
    rs1 = c.pin("RS1", "1")
    c.io("+5V_LED_IN", "left", from_pt=(rs1[0] / cec_sch.GRID, rs1[1] / cec_sch.GRID))
    c.use(("RS1", "1"))

    c.place("U4", 60, 30)
    c.place("C3", 60, 55)
    c.io("ISENSE_TOTAL", "right")
    c.caption("Total-rail shunt + INA180A2 (50V/V) -> +5V_LED (spec Sec 7.4)", 10, 4)
    c.note("+5V_LED_IN's non-anchor member (U4 IN+) and every +5V_LED member "
           "(RS1/U4 VS+IN-/C3) are plain same-name labels/global labels -- "
           "the shunt's own terminal copper IS the Kelvin tap (layout, Sec 6.8)",
           10, 70)
    c.done()


def compose_hub_link(c, lf):
    c.place("J2", 20, 50)
    j1, j2, j3, j6, j8 = (c.pin("J2", "1"), c.pin("J2", "2"), c.pin("J2", "3"),
                          c.pin("J2", "6"), c.pin("J2", "8"))
    c.io("CAN_H_RJ", "right", from_pt=(j3[0] / cec_sch.GRID, j3[1] / cec_sch.GRID))
    c.io("CAN_L_RJ", "right", from_pt=(j6[0] / cec_sch.GRID, j6[1] / cec_sch.GRID))

    # VCC_RJ45_RAW -> FB1 (5VSB entry bead) -> +5VSB_RJ (exit right)
    c.place("FB1", 45, 20)
    fb1a, fb1b = c.pin("FB1", "1"), c.pin("FB1", "2")
    c.wire(j1, (j1[0], fb1a[1]), fb1a)
    c.use(("J2", "1"), ("FB1", "1"))
    c.io("+5VSB_RJ", "right", from_pt=(fb1b[0] / cec_sch.GRID, fb1b[1] / cec_sch.GRID))

    # DETECT chain: J2.8 -- D1 (ESD, shunt to GND) -- R4 (2.2k code, shunt to
    # GND) -- R5 (100k poke tap, series) -- DETECT_SENSE (exit right)
    end = arch.protection_chain(
        c, (j8[0] / cec_sch.GRID, j8[1] / cec_sch.GRID),
        [("shunt", "D1"), ("shunt", "R4"), ("series", "R5")],
        "DETECT_SENSE", out_kind="none", node_label="DETECT", pitch=8)
    c.use(("J2", "8"))
    c.io("DETECT_SENSE", "right", from_pt=end)

    c.caption("RJ-45 FTP + DETECT (2.2k CAN-only code) + 5VSB entry bead "
              "(spec Sec 2.1/2.3/2.4/7.5)", 10, 8)
    c.done()


def compose_can(c, lf):
    c.place("U2", 45, 40)
    u2_3, u2_5 = c.pin("U2", "3"), c.pin("U2", "5")
    c.place("C4", 70, 20)
    c.wire(u2_3, (u2_3[0], 20))
    c.use(("U2", "3"), ("C4", "1"))
    c.io("+5VSB_RJ", "left", from_pt=(u2_3[0] / cec_sch.GRID, u2_3[1] / cec_sch.GRID))
    c.place("C5", 70, 60)
    c.wire(u2_5, (u2_5[0], 60))
    c.use(("U2", "5"), ("C5", "1"))

    c.place("FL1", 15, 70)
    c.place("R6", 15, 90)
    c.place("R7", 35, 90)
    fl1, fl2, fl3, fl4 = (c.pin("FL1", "1"), c.pin("FL1", "2"),
                          c.pin("FL1", "3"), c.pin("FL1", "4"))
    r6a, r6b = c.pin("R6", "1"), c.pin("R6", "2")
    r7a, r7b = c.pin("R7", "1"), c.pin("R7", "2")
    u2_7, u2_6 = c.pin("U2", "7"), c.pin("U2", "6")
    # CAN_H: FL1.1 (RJ side) -bypass R6- FL1.3 (xcvr side) -> U2.7
    c.wire(fl1, (fl1[0], r6a[1]), r6a)
    c.wire(fl3, (fl3[0], r6b[1]), r6b)
    c.wire(fl3, (fl3[0] + 10, fl3[1]), (fl3[0] + 10, u2_7[1]), u2_7)
    c.use(("FL1", "1"), ("FL1", "3"), ("R6", "1"), ("R6", "2"), ("U2", "7"))
    c.io("CAN_H_RJ", "left", from_pt=(fl1[0] / cec_sch.GRID, fl1[1] / cec_sch.GRID))
    # CAN_L: FL1.2 (RJ side) -bypass R7- FL1.4 (xcvr side) -> U2.6
    c.wire(fl2, (fl2[0], r7a[1]), r7a)
    c.wire(fl4, (fl4[0], r7b[1]), r7b)
    c.wire(fl4, (fl4[0] + 14, fl4[1]), (fl4[0] + 14, u2_6[1]), u2_6)
    c.use(("FL1", "2"), ("FL1", "4"), ("R7", "1"), ("R7", "2"), ("U2", "6"))
    c.io("CAN_L_RJ", "left", from_pt=(fl2[0] / cec_sch.GRID, fl2[1] / cec_sch.GRID))

    c.io("CAN_TX", "right")
    c.io("CAN_RX", "right")
    c.caption("TJA1051T/3, classical 500k, no module termination; FL1 CAN CMC "
              "position DNP with the H3a-PATTERN 0R bypasses R6/R7 "
              "(spec Sec 3.1/7.5)", 10, 4)
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
    c.wire(j_vbus, (j_vbus[0], d5_1[1] - 6), (d5_1[0], d5_1[1] - 6), d5_1)
    c.wire(j_vbus, (j_vbus[0], fb2_1[1]), fb2_1)
    c.use(("J3", "A4"), ("D5", "1"), ("FB2", "1"))
    c.use(("J3", "A9"), ("J3", "B4"), ("J3", "B9"))   # coincident VBUS pins

    fb2_2, c10_1 = c.pin("FB2", "2"), c.pin("C10", "1")
    c.wire(fb2_2, c10_1)
    c.use(("FB2", "2"), ("C10", "1"))
    c.io("VBUS", "right", from_pt=(fb2_2[0] / cec_sch.GRID, fb2_2[1] / cec_sch.GRID))

    d6_1, d6_3 = c.pin("D6", "1"), c.pin("D6", "3")
    c.io("USB_D_P", "left", from_pt=(d6_1[0] / cec_sch.GRID, d6_1[1] / cec_sch.GRID))
    c.io("USB_D_N", "left", from_pt=(d6_3[0] / cec_sch.GRID, d6_3[1] / cec_sch.GRID))

    cc1, cc2 = c.pin("J3", "A5"), c.pin("J3", "B5")
    r18_1, r19_1 = c.pin("R18", "1"), c.pin("R19", "1")
    c.wire(cc1, (cc1[0], r18_1[1]), r18_1)
    c.wire(cc2, (cc2[0], r19_1[1]), r19_1)
    c.use(("J3", "A5"), ("J3", "B5"), ("R18", "1"), ("R19", "1"))

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
    arch.pullup_hang(c, en, en[0] + 40, "R8", rx=en[0] + 30, rail_pin="1", above=True)
    c.use(("U1", "45"))
    sw2a = c.pin("SW2", "1")
    c.wire((en[0] + 40, en[1]), (en[0] + 40, sw2a[1]), sw2a)
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
    for (dk, _da) in ((d2k, d2a), (d3k, d3a), (d4k, d4a)):
        pass
    c.wire(d2k, (orx, d2k[1]))
    c.wire(d3k, (orx, d3k[1]))
    c.wire(d4k, (orx, d4k[1]))
    c.wire((orx, d2k[1]), (orx, d4k[1]))
    c.wire((orx, d3k[1]), u3in)
    c.use(("D2", "1"), ("D3", "1"), ("D4", "1"), ("U3", "1"))
    c.io("+5V_LED", "left", from_pt=(d2a[0] / cec_sch.GRID, d2a[1] / cec_sch.GRID))
    c.io("+5VSB_RJ", "left", from_pt=(d3a[0] / cec_sch.GRID, d3a[1] / cec_sch.GRID))
    c.io("VBUS", "left", from_pt=(d4a[0] / cec_sch.GRID, d4a[1] / cec_sch.GRID))

    c.place("C8", 66, 50)
    c.wire(u3in, (u3in[0], 50))
    c.use(("C8", "1"))
    u3out = c.pin("U3", "5")
    c.place("C9", 66, 70)
    c.wire(u3out, (u3out[0], 70))
    c.use(("U3", "5"), ("C9", "1"))

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
        rx = _o_pt[0] / G_ + sgn * 16

        c.place(r, rx, y, 90)
        opin = c.pin("U5", out_pin)
        r1 = c.pin(r, "1")
        c.wire(opin, (r1[0], opin[1]), r1)
        c.use(("U5", out_pin), (r, "1"))

        r2 = c.pin(r, "2")
        c.place(dclamp, rx + sgn * 16, y - 6, 270)
        c.place(dtvs, rx + sgn * 26, y, 270)
        c.place(j, rx + sgn * 44, y)
        d3 = c.pin(dclamp, "3")
        d1 = c.pin(dtvs, "1")
        jp3 = c.pin(j, "3")
        c.wire(r2, (d3[0], r2[1]), d3)
        c.wire(d3, (d1[0], d3[1]), d1)
        c.wire(d1, (jp3[0], d1[1]), jp3)
        c.use((r, "2"), (dclamp, "3"), (dtvs, "1"), (j, "3"))

        d2 = c.pin(dclamp, "2")
        jp1 = c.pin(j, "1")
        c.wire(d2, (d2[0], jp1[1] - 4), (jp1[0], jp1[1] - 4), jp1)
        c.use((dclamp, "2"), (j, "1"))
        d1g = c.pin(dtvs, "2")
        jp4 = c.pin(j, "4")
        c.wire(d1g, (d1g[0], jp4[1] + 4), (jp4[0], jp4[1] + 4), jp4)
        c.use((dtvs, "2"), (j, "4"))
        dclamp1 = c.pin(dclamp, "1")
        c.wire(dclamp1, (dclamp1[0] - sgn * 6, dclamp1[1]))
        c.use((dclamp, "1"))

        _i_pt, (idx, _idy) = c.pin_out("U5", in_pin)
        ipin = c.pin("U5", in_pin)
        c.io(f"LED{ch}_DATA", "left" if idx < 0 else "right",
             from_pt=(ipin[0] / G_, ipin[1] / G_))
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
    c.io("STATUS_LED_DATA", "left", from_pt=((u6a[0] - 6) / cec_sch.GRID, u6a[1] / cec_sch.GRID))

    u6y, r20a = c.pin("U6", "4"), c.pin("R20", "1")
    c.wire(u6y, (r20a[0], u6y[1]), r20a)
    c.use(("U6", "4"), ("R20", "1"))
    r20b, dl3 = c.pin("R20", "2"), c.pin("DL1", "3")
    c.wire(r20b, (r20b[0], dl3[1]), dl3)
    c.use(("R20", "2"), ("DL1", "3"))

    u6vcc = c.pin("U6", "5")
    c.wire(u6vcc, (u6vcc[0], 10))
    c.use(("U6", "5"), ("C11", "1"))

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
BOX = {
    "01-power-input": (4,   8,   170, 100),
    "02-sense":        (4,   130, 110, 50),
    "03-hub-link":     (4,   200, 110, 60),
    "04-can":          (4,   280, 130, 100),
    "07-usb-flash":    (4,   400, 170, 100),
    "05-mcu":          (220, 8,   190, 260),
    "06-led-outputs":  (450, 8,   260, 300),
    "08-status":       (450, 330, 130, 60),
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
            global_nets={"+5V_LED"} if lid in ("02-sense", "05-mcu", "06-led-outputs") else None,
            name_pin_nets=name_pin_nets.get(lid), rev=REV)
        n_moved, still = L.nudge_texts(out_path)
        st["nudged"], st["text_overlaps_left"] = n_moved, still
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
    # appear in exactly one OTHER leaf's hier_exports too); the one true
    # N-way bus (+5V_LED) is handled via global_nets above and carries NO
    # sheet pin at all (a real KiCad global_label connects it project-wide).
    GLOBAL_NET_NAMES = {"+5V_LED"}
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
            "GND/+3V3 are global power nets (per-leaf symbols); +5V_LED is a "
            "genuine 3-leaf bus (global_label, project-wide); every other "
            "crossing is a real drawn sheet-pin lane carrying its exact net name."))
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
