#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Generates the modules/ent-common ESP32-P4 + T1 shared module reference block
# as a GENUINE HIERARCHY (restructured 2026-07-03 from the original flat
# single-sheet capture, per the owner's 2026-07-02 format correction --
# "each functional block literally on its own sheet"):
#
#   p4-t1-block.kicad_sch          root = thin parent (sheet symbols only)
#     01-power.kicad_sch           RJ-45 jack + TPS26621 eFuse + LP5907 3V3 LDO
#     02-misplug-protection.kicad_sch  DETECT chain + pin-7 SYNC/FREEZE chain
#     03-can.kicad_sch             TJA1051T/3 CAN transceiver
#     04-mcu.kicad_sch             ESP32-P4 + W25Q flash + XTAL + decoupling
#     05-t1-phy.kicad_sch          DP83TC814S-Q1 + CMC + AC-couple + ESD
#     06-usb-debug.kicad_sch       USB-C flash/debug front end
#
# Built through the SHARED composition engine (scripts/cec_sch_compose.py:
# Leaf/Compose/build_leaf/build_thin_parent -- the root here IS the thin
# parent, own_sheet_sym_uuid=None) + the T4 archetypes
# (scripts/cec_sch_archetypes.py: protection_chain, divider_chain,
# protected_rail, crystal_block, decoupler_bank, pullup_hang), mirroring
# hubs/hub-enterprise/gen_hub_enterprise.py. ELECTRICAL CONTENT IS UNCHANGED
# from the flat capture: same parts, same values, same footprints, same
# connectivity (verified by flattened-netlist node-set equivalence against
# the committed single-sheet baseline + check_p4_t1_block.py).
#
# All the original engineering flags (RMII pin placeholders, crystal
# frequencies, TPS26621 app values, etc.) still apply -- see README.md's
# 11 numbered FLAGS.
#
#   python3 modules/ent-common/gen_p4_t1_block.py
#
# Validate: python3 modules/ent-common/check_p4_t1_block.py
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTDIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOTDIR, "scripts"))
import cec_sch            # noqa: E402
import cec_sch_layout     # noqa: E402
import cec_sch_compose    # noqa: E402
import cec_sch_archetypes as arch  # noqa: E402

PROJECT = "p4-t1-block"

# Fixed identity uuids (stable across regenerations). ROOT_UUID is the
# PRE-RESTRUCTURE flat file's own uuid, preserved so the project root keeps
# its identity through the re-sheeting.
ROOT_UUID = "592327a8-97c7-4f5c-98e4-af7919494f5a"
LEAF_SYM_UUIDS = {
    "01": "3c4d5e6f-7081-42b1-9c3b-4e5f60718201",
    "02": "3c4d5e6f-7081-42b2-9c3b-4e5f60718202",
    "03": "3c4d5e6f-7081-42b3-9c3b-4e5f60718203",
    "04": "3c4d5e6f-7081-42b4-9c3b-4e5f60718204",
    "05": "3c4d5e6f-7081-42b5-9c3b-4e5f60718205",
    "06": "3c4d5e6f-7081-42b6-9c3b-4e5f60718206",
}
LEAF_OWN_UUIDS = {
    "01": "4d5e6f70-8192-43c1-8d4c-5f60718293a1",
    "02": "4d5e6f70-8192-43c2-8d4c-5f60718293a2",
    "03": "4d5e6f70-8192-43c3-8d4c-5f60718293a3",
    "04": "4d5e6f70-8192-43c4-8d4c-5f60718293a4",
    "05": "4d5e6f70-8192-43c5-8d4c-5f60718293a5",
    "06": "4d5e6f70-8192-43c6-8d4c-5f60718293a6",
}

LIBS = {
    "cec":            open(f"{ROOTDIR}/lib/cec.kicad_sym").read(),
    "cec-vendor":     open(f"{ROOTDIR}/lib/vendor/cec-vendor.kicad_sym").read(),
    "power":          open(f"{ROOTDIR}/lib/vendor/cec-power.kicad_sym").read(),
    "cec-ent-mcu":    open(f"{ROOTDIR}/lib/cec-ent-mcu.kicad_sym").read(),
    "cec-ent-net":    open(f"{ROOTDIR}/lib/cec-ent-net.kicad_sym").read(),
    "cec-ent-power":  open(f"{ROOTDIR}/lib/cec-ent-power.kicad_sym").read(),
    "ent-common-local": open(f"{HERE}/ent-common-local.kicad_sym").read(),
}

POWER_PORTS = {"GND": "GND", "+5VSB": "+5VSB", "+3V3": "+3V3"}


# ---------------------------------------------------------------------------
# ESP32-P4 name -> pin-number lookup (unchanged from the flat generator).
def name_to_number(block):
    m = {}
    for mm in re.finditer(r'\(pin\s+\S+\s+\S+\s*\(at[^)]*\)\s*\(length[^)]*\)', block):
        seg = block[mm.start(): mm.start() + 400]
        nm = re.search(r'\(name "([^"]+)"', seg)
        nu = re.search(r'\(number "([^"]+)"', seg)
        if nm and nu:
            m[nm.group(1)] = nu.group(1)
    return m

P4_BLOCK = cec_sch.symbol_block(LIBS["cec-ent-mcu"], "ESP32-P4")
P4 = name_to_number(P4_BLOCK)

# GPIO assignment -- ALL PLACEHOLDER / TENTATIVE (README flag #1), unchanged.
GP = {
    "CAN_TX":        P4["GPIO1"],
    "CAN_RX":        P4["GPIO2"],
    "DETECT_SENSE":  P4["GPIO3"],
    "PIN7_SYNC":     P4["GPIO4"],
    "MDC":           P4["GPIO5"],
    "MDIO":          P4["GPIO6"],
    "RMII_REFCLK":   P4["GPIO7"],   # ** flagged: REF_CLK pin/sourcing unconfirmed **
    "RMII_RXD0":     P4["GPIO8"],
    "RMII_RXD1":     P4["GPIO9"],
    "RMII_CRS_DV":   P4["GPIO10"],
    "RMII_TXD0":     P4["GPIO11"],
    "RMII_TXD1":     P4["GPIO12"],
    "RMII_TXEN":     P4["GPIO13"],
    "RMII_RXER":     P4["GPIO14"],
    "PHY_RESET_N":   P4["GPIO15"],
    "PHY_INT_N":     P4["GPIO16"],
}

# +3V3 MCU power-pin bundle (README flag #3), unchanged.
P4_VDD_3V3 = ["VDD_HP_0", "VDD_HP_1", "VDD_HP_2", "VDD_HP_3",
              "VDD_IO_0", "VDD_IO_4", "VDD_IO_5", "VDD_IO_6",
              "VDD_LP", "VDD_ANA", "VDD_BAT", "VDD_LDO", "VDD_DCDCC",
              "VDD_USBPHY", "VDD_MIPI_DPHY", "VDD_PSRAM_0", "VDD_PSRAM_1",
              "VDDO_FLASH", "VDDO_PSRAM", "VDDO_3", "VDDO_4", "VDD_FLASHIO"]

FOOTPRINTS = {
    "J1": "cec:RJ45_FTP_Shielded_Horizontal",
    "U1": "cec-ent-mcu:QFN-104_L10.0-W10.0-P0.35-TL-EP7.5",
    "U2": "cec-Package_DFN_QFN:VSON-10_DRC0010J_L3.0-W3.0-P0.50-EP",
    "U3": "cec-Package_TO_SOT_SMD:SOT-23-5",
    "U4": "cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "U5": "cec-Package_SO:SOIC-16_W25Q256JVFIQ_L10.3-W7.5-P1.27",
    "U6": "cec-Package_DFN_QFN:QFN-36-1EP_6x6mm_P0.5mm_EP4.1x4.1mm",
    "L1": "cec-ent-net:FILTER-SMD_4P-L3.2-W2.5-BL_ACT1210",
    "D4": "cec-Package_TO_SOT_SMD:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR",
    "J2": "cec-Connector_USB:USB_C_Receptacle_XKB_U262-16XN-4BVC11",
    "SW1": "cec-Button_Switch_SMD:TS-1088-AR02016",
    "SW2": "cec-Button_Switch_SMD:TS-1088-AR02016",
    "D1": "cec-Diode_SMD:D_SOD-323",
    "D2": "cec-Diode_SMD:D_SOD-323",
    "D3": "cec-Diode_SMD:D_SMA",
    "Y1": "",   # no real footprint yet -- README flag #5
    "Y2": "",
}
def fp_for(ref, lib, name, val):
    if ref in FOOTPRINTS:
        return FOOTPRINTS[ref]
    if name == "R_Small":
        return "cec-Resistor_SMD:R_0402_1005Metric"
    if name == "C_Small":
        return {"10u": "cec-Capacitor_SMD:C_0805_2012Metric",
                "1u":  "cec-Capacitor_SMD:C_0603_1608Metric"}.get(
                    val, "cec-Capacitor_SMD:C_0402_1005Metric")
    return ""


Leaf = cec_sch_compose.Leaf
LEAVES = {}

def leaf(id_, filename, sheetname, desc):
    lf = Leaf(id_, filename, sheetname, desc)
    LEAVES[id_] = lf
    return lf

def ap(lf, ref, lib, name, val):
    """add_part with a dummy position (the compose pass places everything)."""
    lf.add_part(ref, lib, name, val, 0, 0, fp_for(ref, lib, name, val))


# ===========================================================================
# 01 -- power: RJ-45 jack + TPS26621 eFuse (survey 11 / REQ-MOD-COMMON-053)
#       + LP5907 3V3 LDO. Jack pins 3-8 export to the other leaves.
# ===========================================================================
L01 = leaf("01", "01-power.kicad_sch", "01-power",
           "RJ-45 VCC -> TPS26621 eFuse -> LP5907 3V3 LDO (REQ-MOD-COMMON-053); jack pin fan-out")
# J1 uses the ent-common-local WIDENED copy of cec:CEC_RJ45_8P8C_FTP (same
# pin numbers/names/footprint; body 25.4mm wide so the STREAM_P/STREAM_N and
# SHIELD pin-name glyphs no longer interleave -- standard S6; the shared
# lib/cec.kicad_sym original is untouched, a dozen boards embed it)
ap(L01, "J1", "ent-common-local", "CEC_RJ45_8P8C_FTP", "TO-HUB")
ap(L01, "U2", "cec-ent-power", "TPS26621DRCT", "TPS26621DRCT")
ap(L01, "R1", "cec-vendor", "R_Small", "100k")   # UVLO divider top [placeholder]
ap(L01, "R2", "cec-vendor", "R_Small", "20k")    # UVLO divider bottom
ap(L01, "R3", "cec-vendor", "R_Small", "100k")   # OVP divider top [placeholder]
ap(L01, "R4", "cec-vendor", "R_Small", "10k")    # OVP divider bottom
ap(L01, "R5", "cec-vendor", "R_Small", "10k")    # ILIM set [placeholder]
ap(L01, "C1", "cec-vendor", "C_Small", "1n")     # dVdT slew cap [placeholder]
ap(L01, "R6", "cec-vendor", "R_Small", "10k")    # FLT pull-up -> +3V3
ap(L01, "C2", "cec-vendor", "C_Small", "1u")     # eFuse IN bulk
ap(L01, "C3", "cec-vendor", "C_Small", "1u")     # eFuse OUT bulk
ap(L01, "U3", "cec-vendor", "LP5907MFX-1.2", "LP5907MFX-3.3")
ap(L01, "C4", "cec-vendor", "C_Small", "1u")     # LDO VIN bulk
ap(L01, "C5", "cec-vendor", "C_Small", "1u")     # LDO VOUT bulk

L01.net("+5VSB", ("J1", "1"), ("U2", "1"), ("C2", "1"), ("R1", "1"), ("R3", "1"),
        ("U2", "4"))                              # SHDN strapped to its own input rail
L01.net("+5VSB_FUSED", ("U2", "10"), ("C3", "1"), ("U3", "1"), ("U3", "3"), ("C4", "1"))
L01.net("+3V3", ("U3", "5"), ("C5", "1"), ("R6", "1"))
L01.net("GND", ("J1", "2"), ("J1", "SH1"), ("J1", "SH2"),
        ("U2", "5"), ("U2", "6"), ("U2", "11"),
        ("R2", "2"), ("R4", "2"), ("R5", "2"), ("C1", "2"),
        ("U3", "2"), ("C2", "2"), ("C3", "2"), ("C4", "2"), ("C5", "2"))
L01.net("EF_UVLO", ("U2", "2"), ("R1", "2"), ("R2", "1"))
L01.net("EF_OVP",  ("U2", "3"), ("R3", "2"), ("R4", "1"))
L01.net("EF_ILIM", ("U2", "7"), ("R5", "1"))
L01.net("EF_DVDT", ("U2", "8"), ("C1", "1"))
L01.net("EF_FLT",  ("U2", "9"), ("R6", "2"))
L01.net("CAN_H",      ("J1", "3"))
L01.net("T1_A_RAW",   ("J1", "4"))
L01.net("T1_B_RAW",   ("J1", "5"))
L01.net("CAN_L",      ("J1", "6"))
L01.net("SYNC7_RAW",  ("J1", "7"))
L01.net("DETECT_RAW", ("J1", "8"))
L01.hier_exports = {
    "T1_A_RAW":     ("output", ("J1", "4")),
    "T1_B_RAW":     ("output", ("J1", "5")),
    "DETECT_RAW":   ("output", ("J1", "8")),
    "SYNC7_RAW":    ("output", ("J1", "7")),
    "CAN_H":        ("output", ("J1", "3")),
    "CAN_L":        ("output", ("J1", "6")),
    "+5VSB_FUSED":  ("output", ("U3", "1")),
}
L01.powerflag_nets = ["+5VSB", "GND"]


# ===========================================================================
# 02 -- misplug-protection: DETECT (pin 8) + pin-7 SYNC/FREEZE chains
# ===========================================================================
L02 = leaf("02", "02-misplug-protection.kicad_sch", "02-misplug-protection",
           "DETECT series-R + 10k ENT code + ESD + poke tap; pin-7 series-R + clamp (REQ-MOD-COMMON-010/013/053)")
ap(L02, "R7", "cec-vendor", "R_Small", "10k")     # DETECT series R_s (survey 11 (c))
ap(L02, "D1", "cec-vendor", "D_Schottky", "PESD5V0S1BA")
ap(L02, "R8", "cec-vendor", "R_Small", "10k")     # DETECT ENT code resistor (10k class)
ap(L02, "R9", "cec-vendor", "R_Small", "100k")    # DETECT poke-and-ack tap
ap(L02, "R10", "cec-vendor", "R_Small", "100")    # pin-7 series R [placeholder]
ap(L02, "D2", "cec-vendor", "D_Schottky", "PESD5V0S1BA")

L02.net("DETECT_RAW", ("R7", "1"))
L02.net("DETECT_A", ("R7", "2"), ("D1", "1"), ("R8", "1"), ("R9", "1"))
L02.net("DETECT_SENSE", ("R9", "2"))
L02.net("SYNC7_RAW", ("R10", "1"))
L02.net("SYNC7", ("R10", "2"), ("D2", "1"))
L02.net("GND", ("D1", "2"), ("R8", "2"), ("D2", "2"))
L02.hier_exports = {
    "DETECT_RAW":   ("output", ("R7", "1")),
    "SYNC7_RAW":    ("output", ("R10", "1")),
    "DETECT_SENSE": ("output", ("R9", "2")),
    "SYNC7":        ("output", ("R10", "2")),
}


# ===========================================================================
# 03 -- can: TJA1051T/3 (pins 3/6, classical 500k)
# ===========================================================================
L03 = leaf("03", "03-can.kicad_sch", "03-can",
           "TJA1051T/3 CAN transceiver, classical 500k, no module-side termination")
ap(L03, "U4", "cec-vendor", "TJA1051T-3", "TJA1051T/3")
ap(L03, "C6", "cec-vendor", "C_Small", "100n")    # CAN VCC bypass
ap(L03, "C7", "cec-vendor", "C_Small", "100n")    # CAN VIO bypass

L03.net("+5VSB_FUSED", ("U4", "3"), ("C6", "1"))
L03.net("+3V3", ("U4", "5"), ("C7", "1"))
L03.net("GND", ("U4", "2"), ("U4", "8"), ("C6", "2"), ("C7", "2"))
L03.net("CAN_TX", ("U4", "1"))
L03.net("CAN_RX", ("U4", "4"))
L03.net("CAN_H", ("U4", "7"))
L03.net("CAN_L", ("U4", "6"))
L03.hier_exports = {
    "CAN_H":       ("output", ("U4", "7")),
    "CAN_L":       ("output", ("U4", "6")),
    "+5VSB_FUSED": ("output", ("U4", "3")),
    "CAN_TX":      ("output", ("U4", "1")),
    "CAN_RX":      ("output", ("U4", "4")),
}

# ===========================================================================
# 04 -- mcu: ESP32-P4 + external QSPI flash + main XTAL + decoupling field
# ===========================================================================
L04 = leaf("04", "04-mcu.kicad_sch", "04-mcu",
           "ESP32-P4 (radio-free uniform ENT MCU) + W25Q QSPI flash + XTAL + BOOT/RESET + decoupling")
ap(L04, "U1", "cec-ent-mcu", "ESP32-P4", "ESP32-P4NRW32")
ap(L04, "U5", "cec-ent-power", "W25Q256JVFIQ", "W25Q256JVFIQ")  # flag #4: oversized placeholder
ap(L04, "C8", "cec-vendor", "C_Small", "100n")   # flash VCC bypass
ap(L04, "Y1", "ent-common-local", "Crystal_Small", "40MHz")     # flag #5: freq UNVERIFIED
ap(L04, "C9", "cec-vendor", "C_Small", "20p")
ap(L04, "C10", "cec-vendor", "C_Small", "20p")
for _i in (11, 12):
    ap(L04, f"C{_i}", "cec-vendor", "C_Small", "10u")
for _i in range(13, 19):
    ap(L04, f"C{_i}", "cec-vendor", "C_Small", "100n")
ap(L04, "R11", "cec-vendor", "R_Small", "10k")   # CHIP_PU pull-up
ap(L04, "R12", "cec-vendor", "R_Small", "10k")   # GPIO0 pull-up
ap(L04, "SW1", "cec-vendor", "SW_Push", "BOOT")
ap(L04, "SW2", "cec-vendor", "SW_Push", "RESET")

L04.net("+3V3", *([("U5", "2"), ("U5", "3"), ("C8", "1"), ("R11", "1"), ("R12", "1")]
                 + [(f"C{i}", "1") for i in range(11, 19)]
                 + [("U1", P4[n]) for n in P4_VDD_3V3]))   # U5.3 = /RESET tie-high (flat fold)
L04.net("GND", *([("U1", P4["GND"]), ("U1", P4["EN_DCDC"]),
                  ("C9", "2"), ("C10", "2"),
                  ("SW1", "1"), ("SW2", "1"), ("U5", "10"), ("C8", "2")]
                 + [(f"C{i}", "2") for i in range(11, 19)]))
L04.net("FLASH_CS",   ("U1", P4["FLASH_CS"]), ("U5", "7"))
L04.net("FLASH_CK",   ("U1", P4["FLASH_CK"]), ("U5", "16"))
L04.net("FLASH_D",    ("U1", P4["FLASH_D"]), ("U5", "15"))
L04.net("FLASH_Q",    ("U1", P4["FLASH_Q"]), ("U5", "8"))
L04.net("FLASH_HOLD", ("U1", P4["FLASH_HOLD"]), ("U5", "1"))
L04.net("FLASH_WP",   ("U1", P4["FLASH_WP"]), ("U5", "9"))
L04.net("XTAL_P", ("U1", P4["XTAL_P"]), ("Y1", "1"), ("C9", "1"))
L04.net("XTAL_N", ("U1", P4["XTAL_N"]), ("Y1", "2"), ("C10", "1"))
L04.net("CHIP_PU", ("U1", P4["CHIP_PU"]), ("R11", "2"), ("SW2", "2"))
L04.net("GPIO0",   ("U1", P4["GPIO0"]), ("R12", "2"), ("SW1", "2"))
for _net, _gp in [("CAN_TX", "CAN_TX"), ("CAN_RX", "CAN_RX"),
                  ("DETECT_SENSE", "DETECT_SENSE"), ("SYNC7", "PIN7_SYNC"),
                  ("PHY_MDC", "MDC"), ("PHY_MDIO", "MDIO"),
                  ("RMII_REFCLK", "RMII_REFCLK"), ("RMII_RXD0", "RMII_RXD0"),
                  ("RMII_RXD1", "RMII_RXD1"), ("RMII_CRS_DV", "RMII_CRS_DV"),
                  ("RMII_TXD0", "RMII_TXD0"), ("RMII_TXD1", "RMII_TXD1"),
                  ("RMII_TXEN", "RMII_TXEN"), ("RMII_RXER", "RMII_RXER"),
                  ("PHY_RESET_N", "PHY_RESET_N"), ("PHY_INT_N", "PHY_INT_N")]:
    L04.net(_net, ("U1", GP[_gp]))
L04.net("USB_D_P", ("U1", P4["USB_DP"]))
L04.net("USB_D_N", ("U1", P4["USB_DM"]))
L04.hier_exports = {n: ("output", ("U1", p)) for n, p in [
    ("DETECT_SENSE", GP["DETECT_SENSE"]), ("SYNC7", GP["PIN7_SYNC"]),
    ("CAN_TX", GP["CAN_TX"]), ("CAN_RX", GP["CAN_RX"]),
    ("USB_D_P", P4["USB_DP"]), ("USB_D_N", P4["USB_DM"]),
    ("PHY_MDC", GP["MDC"]), ("PHY_MDIO", GP["MDIO"]),
    ("PHY_INT_N", GP["PHY_INT_N"]), ("PHY_RESET_N", GP["PHY_RESET_N"]),
    ("RMII_REFCLK", GP["RMII_REFCLK"]), ("RMII_RXD0", GP["RMII_RXD0"]),
    ("RMII_RXD1", GP["RMII_RXD1"]), ("RMII_CRS_DV", GP["RMII_CRS_DV"]),
    ("RMII_TXD0", GP["RMII_TXD0"]), ("RMII_TXD1", GP["RMII_TXD1"]),
    ("RMII_TXEN", GP["RMII_TXEN"]), ("RMII_RXER", GP["RMII_RXER"]),
]}


# ===========================================================================
# 05 -- t1-phy: 100BASE-T1 module link (pins 4/5): CMC -> AC-couple -> PHY
# ===========================================================================
L05 = leaf("05", "05-t1-phy.kicad_sch", "05-t1-phy",
           "DP83TC814S-Q1 100BASE-T1 PHY + ACT1210L CMC + AC-coupling + PESD2ETH100-T ESD (REQ-MOD-COMMON-003)")
ap(L05, "L1", "cec-ent-net", "ACT1210L-201-2P-TL00", "ACT1210L-201-2P-TL00")
ap(L05, "C20", "cec-vendor", "C_Small", "10n")   # AC-coupling A [flag #7]
ap(L05, "C21", "cec-vendor", "C_Small", "10n")   # AC-coupling B
ap(L05, "U6", "cec-ent-net", "DP83TC814S-Q1", "DP83TC814S-Q1")
ap(L05, "D4", "cec-ent-net", "PESD2ETH100-T", "PESD2ETH100-T")
ap(L05, "Y2", "ent-common-local", "Crystal_Small", "25MHz")     # flag #5
ap(L05, "C22", "cec-vendor", "C_Small", "20p")
ap(L05, "C23", "cec-vendor", "C_Small", "20p")
ap(L05, "C24", "cec-vendor", "C_Small", "1u")    # PHY supply bulk
ap(L05, "C25", "cec-vendor", "C_Small", "100n")  # VDDA bypass
ap(L05, "C26", "cec-vendor", "C_Small", "100n")  # VDDMAC bypass
ap(L05, "C27", "cec-vendor", "C_Small", "100n")  # VDDIO bypass
ap(L05, "R15", "cec-vendor", "R_Small", "2k2")   # MDIO pull-up
ap(L05, "R16", "cec-vendor", "R_Small", "10k")   # PHY INT_N pull-up
ap(L05, "R17", "cec-vendor", "R_Small", "10k")   # PHY RESET_N pull-up

L05.net("T1_A_RAW", ("L1", "1"))
L05.net("T1_B_RAW", ("L1", "2"))
L05.net("T1_A_CMC", ("L1", "4"), ("C20", "1"))
L05.net("T1_B_CMC", ("L1", "3"), ("C21", "1"))
L05.net("TRD_P", ("C20", "2"), ("U6", "12"), ("D4", "1"))
L05.net("TRD_M", ("C21", "2"), ("U6", "13"), ("D4", "2"))
L05.net("PHY_XI", ("U6", "5"), ("Y2", "2"), ("C23", "1"))
L05.net("PHY_XO", ("U6", "4"), ("Y2", "1"), ("C22", "1"))
L05.net("+3V3", ("U6", "7"), ("U6", "11"), ("U6", "22"), ("U6", "34"),
        ("C24", "1"), ("C25", "1"), ("C26", "1"), ("C27", "1"),
        ("R15", "1"), ("R16", "1"), ("R17", "1"))
L05.net("GND", ("D4", "3"), ("C22", "2"), ("C23", "2"),
        ("C24", "2"), ("C25", "2"), ("C26", "2"), ("C27", "2"),
        ("U6", "37"), ("U6", "17"), ("U6", "18"))
L05.net("PHY_MDC", ("U6", "1"))
L05.net("PHY_MDIO", ("U6", "36"), ("R15", "2"))
L05.net("PHY_INT_N", ("U6", "2"), ("R16", "2"))
L05.net("PHY_RESET_N", ("U6", "3"), ("R17", "2"))
L05.net("RMII_REFCLK", ("U6", "28"))   # TX_CLK doubles as REF_CLK -- ** flagged **
L05.net("RMII_RXD0", ("U6", "26"))
L05.net("RMII_RXD1", ("U6", "25"))
L05.net("RMII_CRS_DV", ("U6", "15"))
L05.net("RMII_TXD0", ("U6", "33"))
L05.net("RMII_TXD1", ("U6", "32"))
L05.net("RMII_TXEN", ("U6", "29"))
L05.net("RMII_RXER", ("U6", "14"))
L05.hier_exports = {n: ("output", a) for n, a in [
    ("T1_A_RAW", ("L1", "1")), ("T1_B_RAW", ("L1", "2")),
    ("PHY_MDC", ("U6", "1")), ("PHY_MDIO", ("U6", "36")),
    ("PHY_INT_N", ("U6", "2")), ("PHY_RESET_N", ("U6", "3")),
    ("RMII_REFCLK", ("U6", "28")), ("RMII_RXD0", ("U6", "26")),
    ("RMII_RXD1", ("U6", "25")), ("RMII_CRS_DV", ("U6", "15")),
    ("RMII_TXD0", ("U6", "33")), ("RMII_TXD1", ("U6", "32")),
    ("RMII_TXEN", ("U6", "29")), ("RMII_RXER", ("U6", "14")),
]}


# ===========================================================================
# 06 -- usb-debug: USB-C flash/debug front end (platform pattern, verbatim)
# ===========================================================================
L06 = leaf("06", "06-usb-debug.kicad_sch", "06-usb-debug",
           "USB-C 2.0 flash/debug: ORing Schottky into pre-eFuse +5VSB, CC pulldowns (platform pattern)")
ap(L06, "J2", "cec-vendor", "USB_C_Receptacle_USB2.0_16P", "USB-C 2.0")
ap(L06, "D3", "cec-vendor", "D_Schottky", "SS34")
ap(L06, "C19", "cec-vendor", "C_Small", "10u")
ap(L06, "R13", "cec-vendor", "R_Small", "5k1")   # CC1 pulldown
ap(L06, "R14", "cec-vendor", "R_Small", "5k1")   # CC2 pulldown

L06.net("+5VSB", ("D3", "1"))
L06.net("VBUS", ("J2", "A4"), ("J2", "A9"), ("J2", "B4"), ("J2", "B9"),
        ("D3", "2"), ("C19", "1"))
L06.net("USB_D_P", ("J2", "A6"), ("J2", "B6"))
L06.net("USB_D_N", ("J2", "A7"), ("J2", "B7"))
L06.net("USB_CC1", ("J2", "A5"), ("R13", "1"))
L06.net("USB_CC2", ("J2", "B5"), ("R14", "1"))
L06.net("GND", ("J2", "A1"), ("J2", "A12"), ("J2", "B1"), ("J2", "B12"),
        ("J2", "S1"), ("C19", "2"), ("R13", "2"), ("R14", "2"))
L06.hier_exports = {
    "USB_D_P": ("output", ("J2", "A6")),
    "USB_D_N": ("output", ("J2", "A7")),
}

# ===========================================================================
# COMPOSED LAYOUTS -- 1.27mm grid units, cec_sch_compose.Compose convention.
# ===========================================================================
class _Compose(cec_sch_compose.Compose):
    def __init__(self, lf):
        super().__init__(lf, LIBS)


def compose_01():
    """01-power, rebuilt to the composition standard (S1/S2/S3/S8): the raw
    +5VSB flows as ONE horizontal band across the top (jack VCC -> stamp ->
    input cap -> UVLO/OVLO dividers -> IN riser), the widened TPS26621 sits
    below the band, straps hang down-right, the fused rail continues right
    into the LP5907 on a second baseline, and every off-sheet signal gathers
    in an S1 edge column (jack fan-out LEFT, +5VSB_FUSED RIGHT)."""
    c = _Compose(L01)
    # ---- jack (widened ent-common-local RJ45; pins x=16, rows y=47..61)
    c.place("J1", 30, 54)
    c.wire((16, 47), (14, 47), (14, 40))          # VCC exits top-left to band
    c.use(("J1", "1"))
    c.wire((16, 49), (12, 49), (12, 38))          # GND exits above VCC lane
    c.stamp("GND", 12, 38, 180)
    c.use(("J1", "2"))
    # shield tabs: one riser, one stamp (S8)
    c.wire((44, 53), (46, 53))
    c.wire((44, 55), (46, 55))
    c.wire((46, 53), (46, 55), (46, 60))
    c.stamp("GND", 46, 60, 0)
    c.use(("J1", "SH1"), ("J1", "SH2"))
    # jack fan-out: pins 3-8 -> S1 LEFT column (attach = generic stubs)
    for net in ("CAN_H", "T1_A_RAW", "T1_B_RAW", "CAN_L",
                "SYNC7_RAW", "DETECT_RAW"):
        c.io(net, "left")
    # ---- +5VSB band, y=40 (clear of J1's ref/value field stack at y42/44)
    pts = [(14, 40), (28, 40), (48, 40), (56, 40), (64, 40), (70, 40), (72, 40)]
    for a, b in zip(pts, pts[1:]):
        c.wire(a, b)
    c.stamp("+5VSB", 28, 40, 0)
    c.place("C2", 48, 42)                          # pin 1 on the band split
    c.use(("C2", "1"))
    # UVLO + OVP dividers hanging from the band; tap labels name-merge with
    # the TPS26621 pin-stub labels
    for rt, rb, x, tap in (("R1", "R2", 56, "EF_UVLO"),
                           ("R3", "R4", 64, "EF_OVP")):
        c.place(rt, x, 42)                        # pin 1 on the band split
        c.place(rb, x, 48)
        c.text_side[rt] = c.text_side[rb] = "left"
        c.wire((x, 44), (x, 46))                  # rt.2 -> mid tap = rb.1
        c.label(tap, x, 46, 180)
        c.use((rt, "1"), (rt, "2"), (rb, "1"))
    # SHDN strapped to its own input rail (always-armed); IN riser
    c.wire((70, 40), (70, 54), (76, 54))
    c.use(("U2", "4"))
    c.wire((72, 40), (72, 48), (76, 48))
    c.use(("U2", "1"))
    # ---- eFuse (widened TPS26621: side pins at x 76/96, EP at (86,62))
    c.place("U2", 86, 52)
    # RTN (5) + EP (11) tied under the body, one stamp
    c.wire((76, 56), (74, 56), (74, 62), (86, 62))
    c.wire((86, 62), (86, 64))
    c.stamp("GND", 86, 64, 0)
    c.use(("U2", "5"), ("U2", "11"))
    # GND (6) stamped clear above-right
    c.wire((96, 48), (98, 48), (98, 45))
    c.stamp("GND", 98, 45, 180)
    c.use(("U2", "6"))
    # ILIM (7) / dVdT (8) strap hangs (drawn; crossings are mid-segment)
    c.place("R5", 102, 54)
    c.wire((96, 50), (102, 50), (102, 52))
    c.use(("U2", "7"), ("R5", "1"))
    c.place("C1", 99, 58)
    c.wire((96, 52), (99, 52), (99, 56))
    c.use(("U2", "8"), ("C1", "1"))
    # FLT pull-up exits right at pin-row height, keeps its net name
    c.use(("U2", "9"))
    arch.pullup_hang(c, (96, 54), 108, "R6", rx=106, rail_pin="1", above=True,
                     out="EF_FLT", out_kind="label")
    # ---- fused rail: OUT (10) drops to the y=66 baseline and feeds the LDO
    c.wire((96, 56), (98, 56), (98, 66))
    c.wire((98, 66), (104, 66))
    c.place("C3", 104, 68)                        # pin 1 on the rail split
    c.wire((104, 66), (106, 66))
    c.wire((106, 66), (106, 62))                  # io tap for the export
    c.io("+5VSB_FUSED", "right", from_pt=(106, 62))
    c.wire((106, 66), (110, 66))
    c.place("C4", 110, 68)
    c.wire((110, 66), (114, 66))
    c.wire((114, 66), (116, 66))                  # into LP5907 IN
    c.wire((114, 66), (114, 68), (116, 68))       # EN strapped to IN
    c.use(("U2", "10"), ("C3", "1"), ("C4", "1"), ("U3", "1"), ("U3", "3"))
    # ---- LDO on the same baseline (S2: placed BY its IN pin row)
    c.place_pin("U3", "1", 116, 66)
    gnd = c.pin("U3", "2")
    c.wire(gnd, (gnd[0], gnd[1] + 2))
    c.stamp("GND", gnd[0], gnd[1] + 2, 0)
    c.use(("U3", "2"))
    out5 = c.pin("U3", "5")
    c.wire(out5, (130, 66))
    c.place("C5", 130, 68)
    c.wire((130, 66), (134, 66))
    c.wire((134, 66), (134, 60))
    c.stamp("+3V3", 134, 60, 0)
    c.use(("U3", "5"), ("C5", "1"))
    # ---- captions + notes (S3/S10, from the leaf desc / spec knowledge)
    c.caption("Power entry: RJ-45 VCC -> TPS26621 eFuse -> LP5907 3V3 LDO "
              "(REQ-MOD-COMMON-053)", 10, 32)
    c.note("UVLO 100k/20k, OVP 100k/10k, ILIM 10k, dVdT 1n -- all "
           "[placeholder] app values;\nFLT pull-up 10k -> +3V3; SHDN strapped "
           "to its own input rail (always-armed)", 48, 82)
    c.done()


def compose_02():
    """02-misplug, rebuilt: the two protection chains read as two horizontal
    bands inside S11 accent regions; content spaced so the small sheet
    breathes on A4 (S9); all four off-sheet signals in S1 edge columns."""
    c = _Compose(L02)
    end1 = arch.protection_chain(c, (12, 20),
                                 [("series", "R7"), ("shunt", "D1"),
                                  ("shunt", "R8"), ("series", "R9")],
                                 "DETECT_SENSE", out_kind="none",
                                 node_label="DETECT_A", pitch=8)
    c.io("DETECT_RAW", "left", from_pt=(12, 20))
    c.io("DETECT_SENSE", "right", from_pt=end1)
    end2 = arch.protection_chain(c, (12, 44),
                                 [("series", "R10"), ("shunt", "D2")],
                                 "SYNC7", out_kind="none", pitch=8)
    c.io("SYNC7_RAW", "left", from_pt=(12, 44))
    c.io("SYNC7", "right", from_pt=end2)
    c.region("DETECT (pin 8): series R + ENT 10k code + ESD + poke tap",
             8, 12, 62, 34)
    c.region("SYNC/FREEZE (pin 7): series R + ESD clamp", 8, 38, 62, 56)
    c.note("ENT DETECT code class = 10k (CAN+100BASE-T1, spec 2.3); "
           "REQ-MOD-COMMON-010/013/053", 8, 60)
    c.done()


def compose_03():
    """03-can: transceiver with WIRED VCC bypass, MCU-side signals in the S1
    left column, bus pair in the right column."""
    c = _Compose(L03)
    c.place("U4", 30, 30)
    # VCC (3, top): bypass C6 wired at the pin, io tap above
    c.place("C6", 34, 24)
    c.wire((30, 22), (30, 20))
    c.wire((30, 20), (30, 17))
    c.wire((30, 20), (34, 20))
    c.wire((34, 20), (34, 22))
    c.use(("U4", "3"), ("C6", "1"))
    c.io("+5VSB_FUSED", "left", from_pt=(30, 17))
    c.place("C7", 16, 40)       # VIO bypass; +3V3/GND stamps via generic pass
    c.io("CAN_TX", "left")
    c.io("CAN_RX", "left")
    c.io("CAN_H", "right")
    c.io("CAN_L", "right")
    c.caption("CAN -- TJA1051T/3, classical 500 kbps; no module-side "
              "termination (Hub-only split term)", 6, 8)
    c.done()


def compose_04():
    c = _Compose(L04)
    c.place("U1", 56, 62)
    arch.crystal_block(c, "U1", P4["XTAL_P"], P4["XTAL_N"], "Y1", "C9", "C10",
                       side="right", far=12, near=8, drop=8)
    arch.decoupler_bank(c, [f"C{i}" for i in range(11, 19)], 40, 124)
    c.place("U5", 108, 68)   # 4u right: its stub labels must clear U1's pin numbers
    c.place("C8", 98, 84)
    c.place("R11", 92, 124)
    c.place("R12", 104, 124)  # 12u apart: CHIP_PU/GPIO0 stub labels are ~10mm long
    c.place("SW1", 110, 124)
    c.place("SW2", 110, 130)
    # S1: all 18 off-sheet signals gather in edge columns, side chosen by the
    # anchor pin's stub direction (they all exit the P4's left pin column)
    for net, (_shape, (ref, pin)) in L04.hier_exports.items():
        _pt, (dx, _dy) = c.pin_out(ref, pin)
        c.io(net, "left" if dx < 0 else "right")
    c.caption("ESP32-P4 -- the uniform ENT module MCU (radio-free); GPIO map "
              "ALL PLACEHOLDER (README flag #1)", 24, -4)
    c.note("W25Q256JVFIQ = oversized package placeholder (README flag #4); "
           "40 MHz XTAL freq UNVERIFIED (flag #5)", 88, 56)
    c.done()


def compose_05():
    c = _Compose(L05)
    c.place("U6", 50, 60)
    # MDI chain: S1 left-column inputs -> CMC -> AC-coupling caps -> PHY TRD
    # pins (drawn). Both jog lanes stay strictly LEFT of x25, the U6 left-pin
    # stub-end column -- a lane through x25 merges with the RX_ER/RX_DV/GND
    # stub endpoints (measured: it shorted TRD_M into GND on an earlier try)
    c.place("L1", 6, 56)
    c.place("C20", 21, 52, 90)
    c.place("C21", 19, 62, 90)
    c.wire((-3, 52), (-1, 52))
    c.io("T1_A_RAW", "left", from_pt=(-3, 52))
    c.wire((-3, 62), (-1, 62))
    c.io("T1_B_RAW", "left", from_pt=(-3, 62))
    c.wire((13, 52), (16, 52), (19, 52))
    c.label("T1_A_CMC", 16, 52, 0)
    c.wire((23, 52), (23, 44), (28, 44))
    c.label("TRD_P", 23, 44, 180)   # names the chain net; D4's stub label merges
    c.wire((13, 62), (16, 62), (17, 62))
    c.label("T1_B_CMC", 16, 62, 0)
    c.wire((21, 62), (24, 62), (24, 46), (28, 46))
    c.label("TRD_M", 24, 46, 180)
    c.use(("L1", "1"), ("L1", "2"), ("L1", "3"), ("L1", "4"),
          ("C20", "1"), ("C20", "2"), ("C21", "1"), ("C21", "2"),
          ("U6", "12"), ("U6", "13"))
    # one shared GND tie for the PHY's stacked GND_ESC/GND pins (17/18/37):
    # three per-pin stamps at 2u pitch overlap each other's graphics
    g17, g18, g37 = c.pin("U6", "17"), c.pin("U6", "18"), c.pin("U6", "37")
    gx = g17[0] - 2
    c.wire(g17, (gx, g17[1]))
    c.wire(g18, (gx, g18[1]))
    c.wire(g37, (gx, g37[1]))
    c.wire((gx, g17[1]), (gx, g18[1]))
    c.wire((gx, g18[1]), (gx, g37[1]))
    c.wire((gx, g37[1]), (gx, g37[1] + 3))
    c.stamp("GND", gx, g37[1] + 3, 0)
    c.use(("U6", "17"), ("U6", "18"), ("U6", "37"))
    # PHY-side ESD across TRD_P/TRD_M -- label-tied, placed clear below the chain
    c.place("D4", 8, 68, 90)
    # PHY crystal + load caps -- far/near pushed out so the load-cap GND
    # stamps clear the ang-180 TRD_P/TRD_M chain labels (S6 gate)
    arch.crystal_block(c, "U6", "4", "5", "Y2", "C22", "C23",
                       side="left", far=17, near=13, drop=2, cap_gap=4)
    # MDIO pull-up: drawn run, export via the S1 right column
    mp = c.pin("U6", "36")
    c.use(("U6", "36"))
    arch.pullup_hang(c, mp, 84, "R15", rx=80, rail_pin="1", above=True)
    c.io("PHY_MDIO", "right", from_pt=(84, mp[1]))
    # INT_N / RESET_N pull-ups detached (label-tied to the io column labels)
    c.place("R16", 40, 8)
    c.place("R17", 54, 8)   # 14u apart: their stub labels are horizontal and ~10mm long
    arch.decoupler_bank(c, ["C24", "C25", "C26", "C27"], 40, 104)
    # remaining exports: side by anchor-pin stub direction (MDC/INT_N/RESET_N/
    # RX group exit the PHY's left column; TX group + REFCLK the right)
    for net in ("PHY_MDC", "PHY_INT_N", "PHY_RESET_N", "RMII_REFCLK",
                "RMII_RXD0", "RMII_RXD1", "RMII_CRS_DV", "RMII_TXD0",
                "RMII_TXD1", "RMII_TXEN", "RMII_RXER"):
        ref, pin = L05.hier_exports[net][1]
        _pt, (dx, _dy) = c.pin_out(ref, pin)
        c.io(net, "left" if dx < 0 else "right")
    c.caption("100BASE-T1 module link -- ACT1210L CMC + AC-couple + "
              "DP83TC814S-Q1 (REQ-MOD-COMMON-003)", 0, -6)
    c.note("AC-coupling 10nF [flag #7]; 25 MHz XTAL freq UNVERIFIED [flag #5];\n"
           "TX_CLK-as-REF_CLK UNCONFIRMED [flag #2]", 0, 112)
    c.done()


def compose_06():
    c = _Compose(L06)
    c.place("J2", 16, 36)
    c.place("D3", 36, 16)
    c.place("C19", 44, 18)
    c.place("R13", 38, 52, 90)   # horizontal: CC labels read left, GND stamps right
    c.place("R14", 38, 58, 90)
    c.io("USB_D_P", "right")
    c.io("USB_D_N", "right")
    c.caption("USB-C 2.0 flash/debug front end (platform pattern)", 4, 6)
    c.note("VBUS ORs into pre-eFuse +5VSB through D3 (SS34); CC1/CC2 5.1k "
           "pulldowns = UFP sink", 4, 68)
    # J2's duplicated VBUS (A4/A9/B4/B9) and GND (A1/A12/B1/B12) pins share ONE
    # symbol connection point each -- one generic stub serves the stack; the
    # duplicates are marked consumed so the generic pass doesn't emit four
    # coincident wires + four coincident labels (the flat sheet's dup-stub
    # artifact). Connectivity is preserved: coincident pins join the single
    # stub's endpoint (verified by the flattened-netlist equivalence check).
    c.use(("J2", "A9"), ("J2", "B4"), ("J2", "B9"),
          ("J2", "B1"), ("J2", "A12"), ("J2", "B12"))
    c.done()

# ===========================================================================
# ROOT (thin parent) geometry -- left-to-right flow: jack/power feeds the
# protection/CAN/USB column, which feeds the MCU, which drives the T1 PHY.
# Every cross-leaf net is a REAL drawn wire between exactly two sheet pins
# (build_thin_parent's 1:1 lane router); GND/+5VSB/+3V3 are global power
# nets (per-leaf symbols, no sheet-pin plumbing).
# ===========================================================================
PARENT_PINS = {
    "01": [("T1_A_RAW", "right"), ("T1_B_RAW", "right"), ("DETECT_RAW", "right"),
           ("SYNC7_RAW", "right"), ("CAN_H", "right"), ("CAN_L", "right"),
           ("+5VSB_FUSED", "right")],
    "02": [("DETECT_RAW", "left"), ("SYNC7_RAW", "left"),
           ("DETECT_SENSE", "right"), ("SYNC7", "right")],
    "03": [("CAN_H", "left"), ("CAN_L", "left"), ("+5VSB_FUSED", "left"),
           ("CAN_TX", "right"), ("CAN_RX", "right")],
    "04": [("DETECT_SENSE", "left"), ("SYNC7", "left"), ("CAN_TX", "left"),
           ("CAN_RX", "left"), ("USB_D_P", "left"), ("USB_D_N", "left"),
           ("PHY_MDC", "right"), ("PHY_MDIO", "right"), ("PHY_INT_N", "right"),
           ("PHY_RESET_N", "right"), ("RMII_REFCLK", "right"),
           ("RMII_RXD0", "right"), ("RMII_RXD1", "right"),
           ("RMII_CRS_DV", "right"), ("RMII_TXD0", "right"),
           ("RMII_TXD1", "right"), ("RMII_TXEN", "right"), ("RMII_RXER", "right")],
    "05": [("T1_A_RAW", "left"), ("T1_B_RAW", "left"), ("PHY_MDC", "left"),
           ("PHY_MDIO", "left"), ("PHY_INT_N", "left"), ("PHY_RESET_N", "left"),
           ("RMII_REFCLK", "left"), ("RMII_RXD0", "left"), ("RMII_RXD1", "left"),
           ("RMII_CRS_DV", "left"), ("RMII_TXD0", "left"), ("RMII_TXD1", "left"),
           ("RMII_TXEN", "left"), ("RMII_RXER", "left")],
    "06": [("USB_D_P", "right"), ("USB_D_N", "right")],
}
BOX = {  # (x, y, w, h) in grid units
    "01": (4, 8, 44, 36),
    "02": (60, 24, 40, 16),
    "03": (60, 56, 40, 22),
    "04": (112, 24, 48, 56),
    "05": (196, 8, 44, 68),
    "06": (60, 88, 40, 14),
}
LEAF_PAPER = {"01": "A4", "02": "A4", "03": "A4", "04": "A3",
              "05": "A4", "06": "A4"}


if __name__ == "__main__":
    for _fn in (compose_01, compose_02, compose_03, compose_04, compose_05,
                compose_06):
        _fn()

    LEAF_ORDER = ["01", "02", "03", "04", "05", "06"]
    total_parts = 0
    for li, lid in enumerate(LEAF_ORDER):
        lf = LEAVES[lid]
        assert {n for n, _s in PARENT_PINS[lid]} == set(lf.hier_exports), lid
        stats = cec_sch_compose.build_leaf(
            lf.parts, lf.nets, lf.footprints, lf.props, lf.placement, lf.nc_skip,
            POWER_PORTS, lf.powerflag_nets, lf.hier_exports, None,
            LIBS, PROJECT,
            path_prefix=f"{ROOT_UUID}/{LEAF_SYM_UUIDS[lid]}",
            sheet_instances_path=LEAF_SYM_UUIDS[lid],
            own_uuid=LEAF_OWN_UUIDS[lid],
            page=str(li + 2), out_path=f"{HERE}/{lf.filename}",
            paper=LEAF_PAPER[lid],
            title=f"CEC ENT module common block: {lf.sheetname}",
            comment1=lf.desc,
            pwr_base=100 * (li + 1), layout=lf.layout)
        total_parts += stats["parts"]
        n_moved, still = cec_sch_layout.nudge_texts(f"{HERE}/{lf.filename}")
        stats["nudged"], stats["text_overlaps_left"] = n_moved, still
        print(f"{lf.filename}  " + "  ".join(f"{k}={v}" for k, v in stats.items()))

    u = cec_sch.GRID
    leaves_for_parent = []
    for li, lid in enumerate(LEAF_ORDER):
        lf = LEAVES[lid]
        bx, by, bw, bh = BOX[lid]
        leaves_for_parent.append({
            "id": lid, "sym_uuid": LEAF_SYM_UUIDS[lid], "filename": lf.filename,
            "sheetname": lf.sheetname, "page": str(li + 2),
            "x": bx * u, "y": by * u, "w": bw * u, "h": bh * u,
            "pins": [(name, lf.hier_exports[name][0], side)
                     for name, side in PARENT_PINS[lid]],
        })

    parent_stats = cec_sch_compose.build_thin_parent(
        leaves_for_parent, set(), PROJECT, ROOT_UUID,
        None,                     # own_sheet_sym_uuid=None: this parent IS the root
        ROOT_UUID, out_path=f"{HERE}/p4-t1-block.kicad_sch",
        title="CEC ENT module common block -- p4-t1-block (root)", paper="A3",
        global_power_exports=None, libs=LIBS, pwr_base=700,
        title_comments=(
            "Root = thin parent: sheet-symbol fan-out/fan-in only, no components "
            "(owner 2026-07-02 format correction)",
            "Shared ESP32-P4 + 100BASE-T1 ENT module block -- designed once, "
            "instantiated x4 by the ENT module families",
            "GND/+5VSB/+3V3 are global power nets (per-leaf symbols); every other "
            "crossing is a drawn sheet-pin wire"))
    print("p4-t1-block.kicad_sch (root thin parent)  "
          + "  ".join(f"{k}={v}" for k, v in parent_stats.items())
          + f"  total_leaf_parts={total_parts}")
