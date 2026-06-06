#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Generate the Hub Standard base schematic from a reviewable netlist.
#
# This places every part and connects them with net labels at the exact pin
# coordinates (no drawn wires/junctions). The PARTS and NETS tables below ARE
# the design intent; edit them and re-run to regenerate. Symbols are read from
# the in-repo libraries (lib/cec.kicad_sym, lib/vendor/cec-vendor.kicad_sym) so
# this is self-contained and reproducible.
#
#   python3 scripts/gen-hub-standard.py
#
# Hand-authored without kicad-cli (KiCad 10 unavailable in CI); validate with
# `kicad-cli sch erc` / open in KiCad 10. Symbol stand-ins: TJA1051T-3 is the
# CAN transceiver (classical, locked spec §3.1 v3.5), LP5907MFX-1.2 body for the -3.3 variant,
# SB120 body for SS14, TPS3839DBZ for TPS3839K33 — values are labeled as the
# intended parts.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_sch

# ---------------------------------------------------------------------------
# STALE — DO NOT RUN against the live board. This generator predates the GUI/
# hand work on hubs/hub-standard: it still describes ESP32-S3-MINI-1 (not the
# WROOM-1), an R1 1 ohm inrush resistor and NO TPS2121 mux, DETECT pull-ups to
# +5VSB (the bug fixed to +3V3), and lacks U5 (mux), D2-D6 (ESD), the blackout
# sense, the flash buttons, and the SK6812 level shifter (U6/R14/C14). Re-running
# it OVERWRITES the schematic with that old, buggy, pre-mux design and breaks the
# routed PCB. The live .kicad_sch is hand-maintained — edit it directly (or splice
# with cec_sch primitives). Set CEC_ALLOW_HUB_REGEN=1 only to bootstrap a brand-
# new board from scratch (then expect to re-do all the post-generator work).
if os.environ.get("CEC_ALLOW_HUB_REGEN") != "1":
    sys.exit("gen-hub-standard.py is STALE; refusing to overwrite the live, "
             "hand-maintained schematic (see header). CEC_ALLOW_HUB_REGEN=1 to override.")

ROOTDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBS = {"cec": open(f"{ROOTDIR}/lib/cec.kicad_sym").read(),
        "cec-vendor": open(f"{ROOTDIR}/lib/vendor/cec-vendor.kicad_sym").read(),
        "power": open(f"{ROOTDIR}/lib/vendor/cec-power.kicad_sym").read()}
OUT = f"{ROOTDIR}/hubs/hub-standard/hub-standard.kicad_sch"

# ---- parts: refdes -> (lib, symbol, value) -------------------------------
PARTS = {
    "J1": ("cec", "CEC_PWR_IN_2P", "5VSB_IN"),
    "J2": ("cec", "CEC_RJ45_8P8C_FTP", "PORT1"),
    "J3": ("cec", "CEC_RJ45_8P8C_FTP", "PORT2"),
    "J4": ("cec", "CEC_RJ45_8P8C_FTP", "PORT3"),
    "J5": ("cec", "CEC_RJ45_8P8C_FTP", "PORT4"),
    "J6": ("cec-vendor", "USB_C_Receptacle_USB2.0_16P", "USB-C"),
    "U1": ("cec-vendor", "ESP32-S3-MINI-1", "ESP32-S3-MINI-1-N16R2"),
    "U2": ("cec-vendor", "TJA1051T-3", "TJA1051T/3"),
    "U3": ("cec-vendor", "LP5907MFX-1.2", "LP5907MFX-3.3"),
    "U4": ("cec-vendor", "TPS3839DBZ", "TPS3839K33"),
    "D1": ("cec-vendor", "SB120", "SS14"),
    "C1": ("cec-vendor", "C_Small", "4700u"),
    "C2": ("cec-vendor", "C_Small", "1u"),
    "C3": ("cec-vendor", "C_Small", "1u"),
    "C4": ("cec-vendor", "C_Small", "100n"),
    "C5": ("cec-vendor", "C_Small", "100n"),
    "C6": ("cec-vendor", "C_Small", "100n"),
    "C7": ("cec-vendor", "C_Small", "4n7"),
    "R1": ("cec-vendor", "R_Small", "1R 1W"),
    "R2": ("cec-vendor", "R_Small", "10k"),
    "R3": ("cec-vendor", "R_Small", "60R"),
    "R4": ("cec-vendor", "R_Small", "60R"),
    "R5": ("cec-vendor", "R_Small", "10k"),
    "R6": ("cec-vendor", "R_Small", "10k"),
    "R7": ("cec-vendor", "R_Small", "10k"),
    "R8": ("cec-vendor", "R_Small", "10k"),
    "R9": ("cec-vendor", "R_Small", "5k1"),
    "R10": ("cec-vendor", "R_Small", "5k1"),
    "DL1": ("cec-vendor", "SK6812MINI", "SK6812MINI-E"),
    "DL2": ("cec-vendor", "SK6812MINI", "SK6812MINI-E"),
    "DL3": ("cec-vendor", "SK6812MINI", "SK6812MINI-E"),
    "DL4": ("cec-vendor", "SK6812MINI", "SK6812MINI-E"),
    "DL5": ("cec-vendor", "SK6812MINI", "SK6812MINI-E"),
    "DL6": ("cec-vendor", "SK6812MINI", "SK6812MINI-E"),
    "DL7": ("cec-vendor", "SK6812MINI", "SK6812MINI-E"),
}

ESP_GND = ["1","2","42","43","46","47","48","49","50","51","52","53","54","55",
           "56","57","58","59","60","61","62","63","64","65"]

# ---- nets: name -> [(refdes, pin), ...] ----------------------------------
NETS = {
    # power input chain: J1 -> inrush R1 -> reverse-pol D1 -> +5VSB rail
    "5VSB_RAW": [("J1","1"), ("R1","1")],
    "5VSB_D":   [("R1","2"), ("D1","2")],   # D1: 2=A(anode), 1=K(cathode)
    "+5VSB":    [("D1","1"), ("C1","1"), ("U3","1"), ("U3","3"), ("C2","1"),
                 ("U2","3"),
                 ("J2","1"), ("J3","1"), ("J4","1"), ("J5","1"),
                 ("DL1","4"), ("DL2","4"), ("DL3","4"), ("DL4","4"),
                 ("DL5","4"), ("DL6","4"), ("DL7","4"),
                 ("R5","1"), ("R6","1"), ("R7","1"), ("R8","1"), ("C5","1")],
    "+3V3":     [("U3","5"), ("C3","1"), ("C4","1"), ("U1","3"),
                 ("U2","5"), ("U4","3"), ("R2","1")],
    "GND":      [("J1","2"), ("J2","2"), ("J3","2"), ("J4","2"), ("J5","2"),
                 ("J6","A1"), ("J6","A12"), ("J6","B1"), ("J6","B12"), ("J6","S1"),
                 ("U2","2"), ("U2","8"), ("U3","2"), ("U4","1"),
                 ("C1","2"), ("C2","2"), ("C3","2"), ("C4","2"), ("C5","2"),
                 ("C6","2"), ("C7","2"),
                 ("DL1","2"), ("DL2","2"), ("DL3","2"), ("DL4","2"),
                 ("DL5","2"), ("DL6","2"), ("DL7","2"),
                 ("R9","2"), ("R10","2")] + [("U1", p) for p in ESP_GND],
    # CAN control (pair 3) to all 4 ports + split termination
    "CAN_TX":  [("U1","21"), ("U2","1")],          # IO17 -> TXD
    "CAN_RX":  [("U1","22"), ("U2","4")],          # IO18 -> RXD
    "CAN_H":   [("U2","7"), ("R3","1"),
                ("J2","3"), ("J3","3"), ("J4","3"), ("J5","3")],
    "CAN_L":   [("U2","6"), ("R4","2"),
                ("J2","6"), ("J3","6"), ("J4","6"), ("J5","6")],
    "CAN_MID": [("R3","2"), ("R4","1"), ("C7","1")],   # 120R split + cap to GND
    # supervisor + reset to ESP32 EN, EN pull-up + cap
    "EN":      [("U1","45"), ("R2","2"), ("C6","1"), ("U4","2")],
    # USB Full Speed (native ESP32-S3) to USB-C
    "USB_DP":  [("U1","24"), ("J6","A6"), ("J6","B6")],
    "USB_DM":  [("U1","23"), ("J6","A7"), ("J6","B7")],
    "USB_VBUS":[("J6","A4"), ("J6","A9"), ("J6","B4"), ("J6","B9")],
    "USB_CC1": [("J6","A5"), ("R9","1")],
    "USB_CC2": [("J6","B5"), ("R10","1")],
    # SK6812 data chain: IO48 -> DL1 -> ... -> DL7
    "LED_DATA":[("U1","30"), ("DL1","3")],
    "LED_D12": [("DL1","1"), ("DL2","3")],
    "LED_D23": [("DL2","1"), ("DL3","3")],
    "LED_D34": [("DL3","1"), ("DL4","3")],
    "LED_D45": [("DL4","1"), ("DL5","3")],
    "LED_D56": [("DL5","1"), ("DL6","3")],
    "LED_D67": [("DL6","1"), ("DL7","3")],
    # DETECT: per-port divider (pull-up to +5VSB) into ESP32 ADC1 (IO1..IO4)
    "DETECT1": [("J2","8"), ("R5","2"), ("U1","5")],
    "DETECT2": [("J3","8"), ("R6","2"), ("U1","6")],
    "DETECT3": [("J4","8"), ("R7","2"), ("U1","7")],
    "DETECT4": [("J5","8"), ("R8","2"), ("U1","8")],
    # service / download button on IO0 (button to GND added on PCB)
    "GPIO0":   [("U1","4")],
}

# GPIO0 is the service/download button pad — a single-pin label by design; do
# not flag it as a no-connect (the button to GND lands at the PCB phase).
NC_SKIP = {("U1", "4")}

# Functional placement (mm). Left-to-right: power-in -> regulation -> MCU ->
# CAN + ports; USB top-right; LED chain across the bottom.
LAYOUT = {
    # power input chain (top-left): J1 -> R1 inrush -> D1 -> bulk C1 -> U3 LDO
    "J1": (40, 40), "R1": (75, 35), "D1": (100, 35), "C1": (125, 45),
    "U3": (155, 40), "C2": (130, 75), "C3": (185, 75),
    # supervisor
    "U4": (155, 110), "R2": (120, 110), "C6": (190, 110),
    # MCU (center)
    "U1": (300, 95),
    # CAN transceiver + split termination (between MCU and ports)
    "U2": (430, 60), "R3": (470, 95), "R4": (470, 120), "C7": (500, 110),
    # 4 RJ-45 ports (right column) + per-port DETECT pull-ups
    "J2": (560, 45), "R5": (535, 70),
    "J3": (560, 95), "R6": (535, 120),
    "J4": (560, 150), "R7": (535, 175),
    "J5": (560, 205), "R8": (535, 230),
    # USB-C host (top, near MCU USB pins) + CC resistors
    "J6": (300, 35), "R9": (250, 40), "R10": (250, 55),
    # CAN-transceiver decoupling sits right at U2; ESP32 bulk near U1
    "C4": (270, 150), "C5": (330, 150),
    # SK6812 LED chain — one aligned row so DOUT->DIN draws as straight wires
    "DL1": (70, 270), "DL2": (97.94, 270), "DL3": (125.88, 270), "DL4": (153.82, 270),
    "DL5": (181.76, 270), "DL6": (209.7, 270), "DL7": (237.64, 270),
}

# LED daisy-chain links are 2-pin and colinear -> draw them as real wires.
WIRE_NETS = ["LED_D12", "LED_D23", "LED_D34", "LED_D45", "LED_D56", "LED_D67"]

used = cec_sch.load_symbols(LIBS, PARTS)
stats = cec_sch.build_schematic(OUT, "hub-standard", PARTS, NETS, used, LIBS,
                                paper="A2",
                                power_ports={"GND": "GND", "+5VSB": "+5VSB", "+3V3": "+3V3"},
                                powerflag_nets=["+5VSB", "GND"],
                                nc_skip=NC_SKIP, placement=LAYOUT, wire_nets=WIRE_NETS)
print(f"wrote {os.path.relpath(OUT, ROOTDIR)}")
print("  " + "  ".join(f"{k}={v}" for k, v in stats.items() if k != "root"))
