#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Generates modules/ent-common/p4-t1-block.kicad_sch -- the SHARED ESP32-P4 + T1
# module reference block (board-program scope: "designed once, instantiated x4"
# by atx-24pin-ENT / eps-8pin-ENT / pcie-8pin-{2,3}port-ENT / 12vhpwr-ENT).
#
# Implements REQ-MOD-COMMON-001/003/010-013/053 (docs/enterprise-requirements/
# module-requirements-common.md) + the §0 delta rows of
# docs/enterprise-requirements/spec-sheets/module-ent-spec-sheets.md:
#   - ESP32-P4 (radio-free, uniform ENT MCU) + external QSPI flash
#   - USB-C flash/debug front end (platform pattern: ORing Schottky + CC
#     pulldowns + BOOT/RESET), reused verbatim from modules/eps-8pin
#   - TPS26621 60V auto-retry eFuse ahead of the 3V3 LDO -- pin-1 5VSB enters
#     THERE (REQ-MOD-COMMON-053)
#   - TJA1051T/3 CAN transceiver (pins 3/6, classical 500k)
#   - DETECT (pin 8): 10 kOhm ENT class + NEW series R (survey 11) + low-cap
#     ESD clamp + the platform poke-and-ack tap
#   - pin 7: NEW SYNC/FREEZE + heartbeat-responder line -- series R + low-cap
#     clamp -> P4 GPIO (REQ-MOD-COMMON-013 / REQ-HUB-COMMON-112/114)
#   - DP83TC814S-Q1 100BASE-T1 PHY on pins 4/5: CMC -> AC-coupling caps ->
#     PHY MDI, PESD2ETH100-T PHY-side ESD, RMII to the P4
#   - RJ-45 FTP jack, SH1/SH2 -> GND
#
# This block is NOT yet run through the T1 schematic-composition/layout engine
# (docs/schematic-quality-charter.md T4, not integrated) -- captured with
# TODAY's primitives (scripts/cec_sch.py: wire stub + net label, exactly the
# generator idiom already used by scripts/gen-modules.py). It regenerates
# cleanly later once T4 lands.
#
#   python3 modules/ent-common/gen_p4_t1_block.py
#
# Validate: kicad-cli sch erc ; kicad-cli sch export netlist ;
#           python3 modules/ent-common/check_p4_t1_block.py
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTDIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOTDIR, "scripts"))
import cec_sch

# ---------------------------------------------------------------------------
# A minimal project-local 2-pin crystal placeholder (mirrors cec-vendor's
# R_Small/C_Small geometry exactly so cec_sch's pin-geometry math needs no
# special-casing). NOT a real vendored part -- no MPN chosen; both crystal
# instances below (P4 main XTAL, PHY XTAL) carry a value flagging the
# frequency as UNVERIFIED against the real datasheets in this session (see
# ent-common-local.kicad_sym's Description + the flags list in the README /
# final report). Real file on disk (mirrors hub-enterprise/lib-local.kicad_sym)
# so the project's own sym-lib-table can resolve it in the GUI too.
LIBS = {
    "cec":            open(f"{ROOTDIR}/lib/cec.kicad_sym").read(),
    "cec-vendor":     open(f"{ROOTDIR}/lib/vendor/cec-vendor.kicad_sym").read(),
    "power":          open(f"{ROOTDIR}/lib/vendor/cec-power.kicad_sym").read(),
    "cec-ent-mcu":    open(f"{ROOTDIR}/lib/cec-ent-mcu.kicad_sym").read(),
    "cec-ent-net":    open(f"{ROOTDIR}/lib/cec-ent-net.kicad_sym").read(),
    "cec-ent-power":  open(f"{ROOTDIR}/lib/cec-ent-power.kicad_sym").read(),
    "ent-common-local": open(f"{HERE}/ent-common-local.kicad_sym").read(),
}

# ---------------------------------------------------------------------------
# ESP32-P4 name -> pin-number lookup (the vendored symbol names every pin
# "GPIO24" etc, but cec_sch nets reference pins by NUMBER; this makes the net
# table below readable/robust instead of hand-copying pin numbers).
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

# GPIO assignment -- ALL PLACEHOLDER / TENTATIVE (flag #1, see README + report):
# the vendored ESP32-P4 symbol carries no alternate-function/IO_MUX annotation,
# so which physical pins actually serve the EMAC/RMII peripheral (and whether
# the 50 MHz REF_CLK needs one specific pin) is NOT confirmed in this session
# against Espressif's ESP32-P4 TRM. These are placeholder assignments to
# produce a wireable, ERC-clean reference block; re-pin at schematic capture.
GP = {
    "CAN_TX":        P4["GPIO1"],
    "CAN_RX":        P4["GPIO2"],
    "DETECT_SENSE":  P4["GPIO3"],   # poke-and-ack ADC tap (REQ-MOD-COMMON-010)
    "PIN7_SYNC":     P4["GPIO4"],   # SYNC/FREEZE + heartbeat responder (REQ-MOD-COMMON-013)
    "MDC":           P4["GPIO5"],
    "MDIO":          P4["GPIO6"],
    "RMII_REFCLK":   P4["GPIO7"],   # ** flagged: exact REF_CLK pin/sourcing unconfirmed **
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

# +3V3 MCU power-pin bundle -- ties every VDD_* rail on the bare-die P4 to one
# board +3V3 supply (flag #3: the real ESP32-P4 power tree very likely needs
# more than one rail -- VDD_DCDCC/EN_DCDC/FB_DCDC imply an internal buck the
# datasheet's own power-architecture section must be consulted for; captured
# here as a first-pass simplification, EN_DCDC strapped to GND = assume
# internal-LDO mode, NOT verified this session).
P4_VDD_3V3 = ["VDD_HP_0", "VDD_HP_1", "VDD_HP_2", "VDD_HP_3",
              "VDD_IO_0", "VDD_IO_4", "VDD_IO_5", "VDD_IO_6",
              "VDD_LP", "VDD_ANA", "VDD_BAT", "VDD_LDO", "VDD_DCDCC",
              "VDD_USBPHY", "VDD_MIPI_DPHY", "VDD_PSRAM_0", "VDD_PSRAM_1",
              "VDDO_FLASH", "VDDO_PSRAM", "VDDO_3", "VDDO_4", "VDD_FLASHIO"]

PARTS = {
    # ---- RJ-45 module-to-Hub link (platform universal interface) ----------
    "J1": ("cec", "CEC_RJ45_8P8C_FTP", "TO-HUB"),

    # ---- Mis-plug fail-safe network (survey 11 / REQ-MOD-COMMON-053) ------
    "U2": ("cec-ent-power", "TPS26621DRCT", "TPS26621DRCT"),   # 60V auto-retry eFuse, pin1 ahead of the LDO
    "R1": ("cec-vendor", "R_Small", "100k"),   # UVLO divider top   [placeholder, TI eq TBD]
    "R2": ("cec-vendor", "R_Small", "20k"),    # UVLO divider bottom
    "R3": ("cec-vendor", "R_Small", "100k"),   # OVP divider top    [placeholder, targets ~6.0-6.2V per survey 11]
    "R4": ("cec-vendor", "R_Small", "10k"),    # OVP divider bottom
    "R5": ("cec-vendor", "R_Small", "10k"),    # ILIM set resistor  [placeholder]
    "C1": ("cec-vendor", "C_Small", "1n"),     # dVdT slew cap      [placeholder]
    "R6": ("cec-vendor", "R_Small", "10k"),    # FLT pull-up -> +3V3
    "C2": ("cec-vendor", "C_Small", "1u"),     # eFuse IN bulk
    "C3": ("cec-vendor", "C_Small", "1u"),     # eFuse OUT bulk

    "R7": ("cec-vendor", "R_Small", "10k"),    # DETECT series R_s (survey 11 (c), illustrative 10k)
    "D1": ("cec-vendor", "D_Schottky", "PESD5V0S1BA"),  # DETECT low-cap ESD clamp (same part family/value as consumer)
    "R8": ("cec-vendor", "R_Small", "10k"),    # DETECT ENT code resistor (10k CAN+100BASE-T1 class, §2.3)
    "R9": ("cec-vendor", "R_Small", "100k"),   # DETECT poke-and-ack tap (platform pattern)

    "R10": ("cec-vendor", "R_Small", "100"),   # pin-7 series R [placeholder -- bench-tune per §6a, preserve <=100ns edge]
    "D2":  ("cec-vendor", "D_Schottky", "PESD5V0S1BA"),  # pin-7 low-cap clamp (supersedes the old 1M bleed-R+SMAJ58A, per hub-ent-bom-detailed.md §6a)

    # ---- Power: eFuse -> 3V3 LDO ------------------------------------------
    "U3": ("cec-vendor", "LP5907MFX-1.2", "LP5907MFX-3.3"),
    "C4": ("cec-vendor", "C_Small", "1u"),   # LDO VIN bulk
    "C5": ("cec-vendor", "C_Small", "1u"),   # LDO VOUT bulk

    # ---- CAN (pins 3/6, classical 500k, TJA1051T/3) -----------------------
    "U4": ("cec-vendor", "TJA1051T-3", "TJA1051T/3"),
    "C6": ("cec-vendor", "C_Small", "100n"),  # CAN VCC bypass
    "C7": ("cec-vendor", "C_Small", "100n"),  # CAN VIO bypass

    # ---- MCU: ESP32-P4 + external QSPI flash + main XTAL ------------------
    "U1": ("cec-ent-mcu", "ESP32-P4", "ESP32-P4NRW32"),
    "U5": ("cec-ent-power", "W25Q256JVFIQ", "W25Q256JVFIQ"),  # flag: oversized/placeholder density, see README
    "C8": ("cec-vendor", "C_Small", "100n"),   # flash VCC bypass
    "Y1": ("ent-common-local", "Crystal_Small", "40MHz"),      # flag: freq UNVERIFIED vs ESP32-P4 datasheet
    "C9": ("cec-vendor", "C_Small", "20p"),
    "C10": ("cec-vendor", "C_Small", "20p"),

    # decoupling field (bulk + spread bypass) -- see README note on scope
    "C11": ("cec-vendor", "C_Small", "10u"),
    "C12": ("cec-vendor", "C_Small", "10u"),
    "C13": ("cec-vendor", "C_Small", "100n"),
    "C14": ("cec-vendor", "C_Small", "100n"),
    "C15": ("cec-vendor", "C_Small", "100n"),
    "C16": ("cec-vendor", "C_Small", "100n"),
    "C17": ("cec-vendor", "C_Small", "100n"),
    "C18": ("cec-vendor", "C_Small", "100n"),

    "R11": ("cec-vendor", "R_Small", "10k"),   # CHIP_PU pull-up -> +3V3
    "R12": ("cec-vendor", "R_Small", "10k"),   # GPIO0 pull-up -> +3V3
    "SW1": ("cec-vendor", "SW_Push", "BOOT"),
    "SW2": ("cec-vendor", "SW_Push", "RESET"),

    # ---- USB-C flash/debug front end (platform pattern, verbatim) --------
    "J2": ("cec-vendor", "USB_C_Receptacle_USB2.0_16P", "USB-C 2.0"),
    "D3": ("cec-vendor", "D_Schottky", "SS34"),
    "C19": ("cec-vendor", "C_Small", "10u"),
    "R13": ("cec-vendor", "R_Small", "5k1"),   # CC1 pulldown
    "R14": ("cec-vendor", "R_Small", "5k1"),   # CC2 pulldown

    # ---- 100BASE-T1 module link (pins 4/5): CMC -> AC-couple -> PHY -------
    "L1": ("cec-ent-net", "ACT1210L-201-2P-TL00", "ACT1210L-201-2P-TL00"),
    "C20": ("cec-vendor", "C_Small", "10n"),   # AC-coupling cap, line A [>=100V rated, exact value/rating pending PHY app note SNLA389A]
    "C21": ("cec-vendor", "C_Small", "10n"),   # AC-coupling cap, line B
    "U6": ("cec-ent-net", "DP83TC814S-Q1", "DP83TC814S-Q1"),
    "D4": ("cec-ent-net", "PESD2ETH100-T", "PESD2ETH100-T"),  # PHY-side ESD (>=100V trigger, inert through the 57V fault)
    "Y2": ("ent-common-local", "Crystal_Small", "25MHz"),      # flag: freq UNVERIFIED vs DP83TC814S-Q1 datasheet
    "C22": ("cec-vendor", "C_Small", "20p"),
    "C23": ("cec-vendor", "C_Small", "20p"),
    "C24": ("cec-vendor", "C_Small", "1u"),    # PHY supply bulk
    "C25": ("cec-vendor", "C_Small", "100n"),  # VDDA bypass
    "C26": ("cec-vendor", "C_Small", "100n"),  # VDDMAC bypass
    "C27": ("cec-vendor", "C_Small", "100n"),  # VDDIO bypass
    "R15": ("cec-vendor", "R_Small", "2k2"),   # MDIO pull-up -> +3V3
    "R16": ("cec-vendor", "R_Small", "10k"),   # PHY INT_N pull-up -> +3V3
    "R17": ("cec-vendor", "R_Small", "10k"),   # PHY RESET_N pull-up -> +3V3
}

NETS = {
    "+5VSB": [("J1", "1"), ("U2", "1"), ("D3", "1"), ("C2", "1"),
              ("R1", "1"), ("R3", "1")],
    "+5VSB_FUSED": [("U2", "10"), ("C3", "1"), ("U3", "1"), ("U3", "3"), ("C4", "1"),
                    ("U4", "3"), ("C6", "1")],
    "+3V3": [("U3", "5"), ("C5", "1"),
             ("U4", "5"), ("C7", "1"),
             ("U5", "2"), ("C8", "1"),
             ("R11", "1"), ("R12", "1"),
             ("R15", "1"), ("R16", "1"), ("R17", "1"),
             ("R6", "1"),
             ("C11", "1"), ("C12", "1"), ("C13", "1"), ("C14", "1"),
             ("C15", "1"), ("C16", "1"), ("C17", "1"), ("C18", "1"),
             ("C24", "1"), ("C25", "1"), ("C26", "1"), ("C27", "1"),
             ("U6", "7"), ("U6", "11"), ("U6", "22"), ("U6", "34"),
             ] + [("U1", P4[n]) for n in P4_VDD_3V3],

    "GND": ([("J1", "2"), ("J1", "SH1"), ("J1", "SH2"),
              ("U2", "5"), ("U2", "6"), ("U2", "11"),
              ("R2", "2"), ("R4", "2"), ("R5", "2"), ("C1", "2"),
              ("D1", "2"), ("D2", "2"), ("R8", "2"),
              ("U3", "2"), ("C2", "2"), ("C3", "2"), ("C4", "2"), ("C5", "2"),
              ("U4", "2"), ("U4", "8"), ("C6", "2"), ("C7", "2"),
              ("U5", "10"), ("C8", "2"),
              ("C9", "2"), ("C10", "2"),
              ("C11", "2"), ("C12", "2"), ("C13", "2"), ("C14", "2"),
              ("C15", "2"), ("C16", "2"), ("C17", "2"), ("C18", "2"),
              ("SW1", "1"), ("SW2", "1"),
              ("J2", "A1"), ("J2", "A12"), ("J2", "B1"), ("J2", "B12"), ("J2", "S1"),
              ("C19", "2"), ("R13", "2"), ("R14", "2"),
              ("D4", "3"),
              ("C22", "2"), ("C23", "2"), ("C24", "2"), ("C25", "2"),
              ("C26", "2"), ("C27", "2"), ("U6", "37"), ("U6", "17"), ("U6", "18"),
              ] + [("U1", P4["GND"]), ("U1", P4["EN_DCDC"])]),

    # ---- mis-plug protection: eFuse app pins ------------------------------
    "EF_UVLO": [("U2", "2"), ("R1", "2"), ("R2", "1")],
    "EF_OVP":  [("U2", "3"), ("R3", "2"), ("R4", "1")],
    "EF_SHDN": [("U2", "4")],           # tied via GND net below (always-armed)
    "EF_ILIM": [("U2", "7"), ("R5", "1")],
    "EF_DVDT": [("U2", "8"), ("C1", "1")],
    "EF_FLT":  [("U2", "9"), ("R6", "2")],   # pull-up half in +3V3; GPIO tap below
    "EF_FLT_SENSE": [("U2", "9")],  # placeholder net alias kept for clarity; real fan-out below

    # ---- DETECT (pin 8): series R -> [ESD clamp + 10k code R + poke tap] --
    "DETECT_RAW": [("J1", "8"), ("R7", "1")],
    "DETECT_A":   [("R7", "2"), ("D1", "1"), ("R8", "1"), ("R9", "1")],
    "DETECT_SENSE": [("R9", "2"), ("U1", GP["DETECT_SENSE"])],

    # ---- pin 7: SYNC/FREEZE + heartbeat responder -------------------------
    "SYNC7_RAW": [("J1", "7"), ("R10", "1")],
    "SYNC7":     [("R10", "2"), ("D2", "1"), ("U1", GP["PIN7_SYNC"])],

    # ---- CAN -------------------------------------------------------------
    "CAN_TX": [("U1", GP["CAN_TX"]), ("U4", "1")],
    "CAN_RX": [("U1", GP["CAN_RX"]), ("U4", "4")],
    "CAN_H":  [("U4", "7"), ("J1", "3")],
    "CAN_L":  [("U4", "6"), ("J1", "6")],

    # ---- MCU flash + XTAL --------------------------------------------------
    "FLASH_CS":   [("U1", P4["FLASH_CS"]), ("U5", "7")],
    "FLASH_CK":   [("U1", P4["FLASH_CK"]), ("U5", "16")],
    "FLASH_D":    [("U1", P4["FLASH_D"]), ("U5", "15")],
    "FLASH_Q":    [("U1", P4["FLASH_Q"]), ("U5", "8")],
    "FLASH_HOLD": [("U1", P4["FLASH_HOLD"]), ("U5", "1")],
    "FLASH_WP":   [("U1", P4["FLASH_WP"]), ("U5", "9")],
    "FLASH_RESET_TIEHIGH": [("U5", "3")],   # tied to +3V3 below (flagged: not sync'd to CHIP_PU)

    "XTAL_P": [("U1", P4["XTAL_P"]), ("Y1", "1"), ("C9", "1")],
    "XTAL_N": [("U1", P4["XTAL_N"]), ("Y1", "2"), ("C10", "1")],

    "CHIP_PU": [("U1", P4["CHIP_PU"]), ("R11", "2"), ("SW2", "2")],
    "GPIO0":   [("U1", P4["GPIO0"]), ("R12", "2"), ("SW1", "2")],

    # ---- USB-C flash/debug (platform pattern) -----------------------------
    "VBUS":    [("J2", "A4"), ("J2", "A9"), ("J2", "B4"), ("J2", "B9"), ("D3", "2"), ("C19", "1")],
    "USB_D_P": [("J2", "A6"), ("J2", "B6"), ("U1", P4["USB_DP"])],
    "USB_D_N": [("J2", "A7"), ("J2", "B7"), ("U1", P4["USB_DM"])],
    "USB_CC1": [("J2", "A5"), ("R13", "1")],
    "USB_CC2": [("J2", "B5"), ("R14", "1")],

    # ---- 100BASE-T1: RJ-45 pins 4/5 -> CMC -> AC-couple -> PHY MDI --------
    "T1_A_RAW": [("J1", "4"), ("L1", "1")],
    "T1_B_RAW": [("J1", "5"), ("L1", "2")],
    "T1_A_CMC": [("L1", "4"), ("C20", "1")],
    "T1_B_CMC": [("L1", "3"), ("C21", "1")],
    "TRD_P":    [("C20", "2"), ("U6", "12"), ("D4", "1")],
    "TRD_M":    [("C21", "2"), ("U6", "13"), ("D4", "2")],

    "PHY_MDC":  [("U1", GP["MDC"]), ("U6", "1")],
    "PHY_MDIO": [("U1", GP["MDIO"]), ("U6", "36"), ("R15", "2")],
    "PHY_INT_N": [("U1", GP["PHY_INT_N"]), ("U6", "2"), ("R16", "2")],
    "PHY_RESET_N": [("U1", GP["PHY_RESET_N"]), ("U6", "3"), ("R17", "2")],
    "PHY_XI": [("U6", "5"), ("Y2", "2"), ("C23", "1")],
    "PHY_XO": [("U6", "4"), ("Y2", "1"), ("C22", "1")],

    "RMII_REFCLK": [("U1", GP["RMII_REFCLK"]), ("U6", "28")],   # TX_CLK doubles as REF_CLK -- ** flagged, unconfirmed **
    "RMII_RXD0":   [("U1", GP["RMII_RXD0"]), ("U6", "26")],
    "RMII_RXD1":   [("U1", GP["RMII_RXD1"]), ("U6", "25")],
    "RMII_CRS_DV": [("U1", GP["RMII_CRS_DV"]), ("U6", "15")],
    "RMII_TXD0":   [("U1", GP["RMII_TXD0"]), ("U6", "33")],
    "RMII_TXD1":   [("U1", GP["RMII_TXD1"]), ("U6", "32")],
    "RMII_TXEN":   [("U1", GP["RMII_TXEN"]), ("U6", "29")],
    "RMII_RXER":   [("U1", GP["RMII_RXER"]), ("U6", "14")],
}

# fold the small "tie to a rail" nets into +3V3 / GND so they don't become
# their own single-purpose stub (matches how gen-modules.py folds EN/DETECT
# taps into shared rails where the intent is simply "tied to this rail").
NETS["+5VSB"] += NETS.pop("EF_SHDN")            # SHDN tied to +5VSB... see note below
NETS["+3V3"] += NETS.pop("FLASH_RESET_TIEHIGH")
NETS["+3V3"] += [("U6", "34")] if False else []  # (no-op; VDDIO already wired above)
del NETS["EF_FLT_SENSE"]

# NOTE on EF_SHDN: TPS26621's SHDN is described active-low-shutdown by most
# TI eFuse families; tying it HIGH (to the raw incoming +5VSB, its own input
# rail) keeps the eFuse always-armed with no separate MCU shutdown control in
# this reference block -- flagged as a placeholder policy (an MCU-controlled
# shutdown GPIO is a reasonable per-family enhancement, not added here since
# ent-common has no MCU-side "kill" signal defined by any REQ yet).

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
    "Y1": "",   # no real footprint yet -- see flags (frequency/part unverified)
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

# ---------------------------------------------------------------------------
# Placement (mm), left-to-right signal flow, A1 paper (the P4 body alone is
# ~46 x 137mm -- this block needs real room). Grouped into charter-style
# annotation boxes even though the T4 composition engine isn't wired in yet.
PLACEMENT = {
    "J1": (60, 380),

    # mis-plug protection cluster, hugs J1
    "R7": (110, 340), "D1": (110, 365), "R8": (140, 365), "R9": (140, 340),
    "R10": (110, 410), "D2": (140, 410),

    # eFuse + LDO power chain
    "U2": (210, 380), "R1": (180, 420), "R2": (180, 440), "R3": (210, 420),
    "R4": (210, 440), "R5": (240, 420), "C1": (240, 440), "R6": (270, 420),
    "C2": (180, 360), "C3": (240, 360),
    "U3": (300, 380), "C4": (280, 400), "C5": (320, 400),

    # CAN
    "U4": (300, 300), "C6": (280, 270), "C7": (320, 270),

    # MCU + flash + XTAL
    "U1": (450, 250),
    "U5": (560, 130), "C8": (560, 100),
    "Y1": (560, 250), "C9": (545, 270), "C10": (575, 270),
    "C11": (560, 300), "C12": (560, 320), "C13": (390, 60), "C14": (390, 80),
    "C15": (390, 100), "C16": (390, 120), "C17": (390, 140), "C18": (390, 160),
    "R11": (390, 400), "R12": (390, 420), "SW1": (420, 420), "SW2": (420, 400),

    # USB-C flash/debug
    "J2": (450, 480), "D3": (410, 480), "C19": (410, 500),
    "R13": (500, 500), "R14": (500, 520),

    # 100BASE-T1: CMC -> coupling -> PHY, right side
    "L1": (620, 380), "C20": (650, 360), "C21": (650, 400),
    "U6": (700, 380), "D4": (740, 380),
    "Y2": (700, 300), "C22": (685, 280), "C23": (715, 280),
    "C24": (700, 440), "C25": (720, 440), "C26": (740, 440), "C27": (760, 440),
    "R15": (700, 260), "R16": (740, 260), "R17": (700, 240),
}

SECTIONS = {
    "MIS-PLUG PROTECTION (survey 11 / REQ-MOD-COMMON-053)": (95, 325, 300, 460),
    "POWER: eFUSE -> 3V3 LDO": (170, 340, 340, 460),
    "CAN (TJA1051T/3)": (270, 250, 340, 300),
    "MCU + FLASH + XTAL": (380, 30, 600, 440),
    "USB-C FLASH/DEBUG": (395, 460, 560, 540),
    "100BASE-T1 (DP83TC814S-Q1 + protection)": (610, 220, 790, 460),
}

if __name__ == "__main__":
    used = cec_sch.load_symbols(LIBS, PARTS)
    fps = {r: fp_for(r, *PARTS[r]) for r in PARTS}
    out = f"{HERE}/p4-t1-block.kicad_sch"
    if not os.path.exists(out):
        # bootstrap stub: build_schematic reads the existing file's root uuid
        # then overwrites it wholesale (same pattern as gen-module-rev2.py).
        import uuid as _uuid
        with open(out, "w") as f:
            f.write(f'(kicad_sch (version 20260306) (generator "eeschema") '
                    f'(generator_version "10.0") (uuid "{_uuid.uuid4()}") (paper "A1"))\n')
    stats = cec_sch.build_schematic(
        out, "p4-t1-block", PARTS, NETS, used, LIBS, paper="A1",
        power_ports={"GND": "GND", "+5VSB": "+5VSB", "+3V3": "+3V3"},
        powerflag_nets=["+5VSB", "GND"],
        placement=PLACEMENT, footprints=fps, sections=SECTIONS,
    )
    print(f"modules/ent-common/p4-t1-block.kicad_sch  " +
          "  ".join(f"{k}={v}" for k, v in stats.items() if k != "root"))
