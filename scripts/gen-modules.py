#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Generate the Standard-tier module schematics (24-pin ATX, EPS 8-pin, PCIe
# 8-pin, 12VHPWR Standard). Shared control/comms/power backbone locked to the
# ESP32-S3-MINI-1, plus per-rail sensing: one INA238 (16-bit I2C current/voltage
# monitor, locked for Standard) per sensed rail — high-side shunt across Vin+/Vin-,
# bus voltage on the dedicated Vbus pin, on a shared I2C bus to the ESP32. The 24-pin module
# senses 4 rails (12V/5V/3V3/5VSB) and carries the dedicated 2-pin +5VSB power-
# out to the Hub (OQ-1); the others sense one 12V rail.
#
# The PARTS/NETS are the netlist (a guard rejects any pin in two nets). The
# physical pass-through power connectors (PSU-side in / load-side out, where each
# sensed rail enters and leaves through its shunt) are the mechanical interposer,
# added at the connector/PCB phase; rails appear here as RAIL*_HI / RAIL*_LO.
#
#   python3 scripts/gen-modules.py
# Hand-authored without kicad-cli; validate with `kicad-cli sch erc`. Symbol
# stand-ins (values labeled as intended): TJA1051T-3 -> TJA1462A,
# LP5907MFX-1.2 body -> -3.3, INA226 body -> INA238.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_sch

ROOTDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBS = {"cec": open(f"{ROOTDIR}/lib/cec.kicad_sym").read(),
        "cec-vendor": open(f"{ROOTDIR}/lib/vendor/cec-vendor.kicad_sym").read(),
        "power": open(f"{ROOTDIR}/lib/vendor/cec-power.kicad_sym").read()}
MODS = [("atx-24pin", "24pin-module"), ("eps-8pin", "eps8pin-module"),
        ("pcie-8pin", "pcie8pin-module"), ("12vhpwr-standard", "12vhpwr-standard-module")]
# rails sensed per module: (rail name, shunt value)
RAILS = {
    "atx-24pin": [("12V","2m"), ("5V","5m"), ("3V3","5m"), ("5VSB","10m")],
    "eps-8pin": [("12V","2m")],
    "pcie-8pin": [("12V","2m")],
    "12vhpwr-standard": [("12V","1m")],
}
# INA238 I2C address strap per sensed-rail index: (A0 net, A1 net)
STRAP = [("GND","GND"), ("+3V3","GND"), ("GND","+3V3"), ("+3V3","+3V3")]
ESP_GND = ["1","2","42","43","46","47","48","49","50","51","52","53","54","55",
           "56","57","58","59","60","61","62","63","64","65"]

# shared control/comms/power backbone
BASE_PARTS = {
    "J1": ("cec", "CEC_RJ45_8P8C_FTP", "TO-HUB"),
    "U1": ("cec-vendor", "ESP32-S3-MINI-1", "ESP32-S3-MINI-1-N16R2"),
    "U2": ("cec-vendor", "TJA1051T-3", "TJA1462A"),
    "U3": ("cec-vendor", "LP5907MFX-1.2", "LP5907MFX-3.3"),
    "R1": ("cec-vendor", "R_Small", "R_ID (OQ-6)"),
    "R2": ("cec-vendor", "R_Small", "10k"),
    "R3": ("cec-vendor", "R_Small", "2k2"),   # I2C SDA pull-up
    "R4": ("cec-vendor", "R_Small", "2k2"),   # I2C SCL pull-up
    "C1": ("cec-vendor", "C_Small", "1u"),
    "C2": ("cec-vendor", "C_Small", "1u"),
    "C3": ("cec-vendor", "C_Small", "100n"),
    "C4": ("cec-vendor", "C_Small", "100n"),
    "C5": ("cec-vendor", "C_Small", "100n"),
}

def build(dirn):
    rails = RAILS[dirn]
    parts = dict(BASE_PARTS)
    for i, (rn, sv) in enumerate(rails):
        parts[f"U1{i}"] = ("cec-vendor", "INA226", "INA238")     # INA226 body = INA238 pinout
        parts[f"RS{i+1}"] = ("cec-vendor", "R_Small", sv)
        parts[f"C1{i}"] = ("cec-vendor", "C_Small", "100n")      # INA238 VS decoupling
    if dirn == "atx-24pin":
        parts["J2"] = ("cec", "CEC_PWR_IN_2P", "TO-HUB-PWR")     # OQ-1 5VSB power-out
    nets = {
        "+5VSB": [("J1","1"),("U3","1"),("U3","3"),("C1","1"),("C4","1"),("U2","3")],
        "+3V3":  [("U3","5"),("C2","1"),("C3","1"),("U1","3"),("U2","5"),("R2","1"),("R3","2"),("R4","2")],
        "GND":   [("J1","2"),("U3","2"),("U2","2"),("U2","8"),("R1","2"),
                  ("C1","2"),("C2","2"),("C3","2"),("C4","2"),("C5","2")] + [("U1",p) for p in ESP_GND],
        "EN":     [("U1","45"),("R2","2"),("C5","1")],
        "CAN_TX": [("U1","21"),("U2","1")],
        "CAN_RX": [("U1","22"),("U2","4")],
        "CAN_H":  [("U2","7"),("J1","3")],
        "CAN_L":  [("U2","6"),("J1","6")],
        "DETECT": [("J1","8"),("R1","1")],
        "GPIO0":  [("U1","4")],
        "I2C_SDA":[("U1","12"),("R3","1")],   # IO8
        "I2C_SCL":[("U1","13"),("R4","1")],   # IO9
    }
    for i, (rn, sv) in enumerate(rails):
        ina = f"U1{i}"; sh = f"RS{i+1}"; dec = f"C1{i}"
        nets[f"RAIL{rn}_HI"] = [(sh,"1"), (ina,"10")]             # supply side, Vin+
        nets[f"RAIL{rn}_LO"] = [(sh,"2"), (ina,"9"), (ina,"8")]   # load side, Vin- + Vbus
        nets["+3V3"]  += [(ina,"6"), (dec,"1")]                   # VS + decoupling
        nets["GND"]   += [(ina,"7"), (dec,"2")]                   # GND
        nets["I2C_SDA"] += [(ina,"4")]
        nets["I2C_SCL"] += [(ina,"5")]
        a0, a1 = STRAP[i]
        nets[a0] += [(ina,"2")]    # A0
        nets[a1] += [(ina,"1")]    # A1
        # Alert (pin 3) left open in the draft
    if dirn == "atx-24pin":
        nets["+5VSB"] += [("J2","1")]
        nets["GND"]   += [("J2","2")]
    return parts, nets

def layout(dirn, parts):
    """Functional placement (mm), left-to-right signal flow:
    col 0  J1 Hub connector (+ J2 power-out on atx)
    col 1  power chain: U3 LDO with C1/C2 bulk; ID/EN passives
    col 2  U2 CAN transceiver
    col 3  U1 ESP32-S3 (center), I2C pull-ups above it
    row 2  INA238 sensing, one (shunt RSn, monitor U1n, decoupling C1n) group per rail
    Unlisted parts fall back to the auto-grid."""
    P = {
        "J1": (50, 70),
        "U3": (150, 55), "C1": (120, 60), "C2": (180, 60),
        "R1": (120, 110), "R2": (180, 110), "C5": (210, 110),
        "U2": (240, 70),
        "U1": (340, 90),
        "R3": (300, 40), "R4": (320, 40),
        "C3": (300, 150), "C4": (390, 60),
    }
    if dirn == "atx-24pin":
        P["J2"] = (50, 120)
    # sensing groups along a lower band, spread by rail index
    for i in range(len(RAILS[dirn])):
        x = 70 + i * 110
        P[f"RS{i+1}"] = (x, 210)        # shunt
        P[f"U1{i}"]   = (x + 45, 210)   # INA238 monitor
        P[f"C1{i}"]   = (x + 90, 210)   # VS decoupling
    return {r: P[r] for r in parts if r in P}

for dirn, base in MODS:
    parts, nets = build(dirn)
    out = f"{ROOTDIR}/modules/{dirn}/{base}.kicad_sch"
    used = cec_sch.load_symbols(LIBS, parts)
    # GPIO0 is the service-button pad — single-pin label by design, no NC flag.
    nc_skip = {("U1", "4")}
    # Power rails use power-PORT symbols (GND triangle, +5VSB/+3V3 bars) instead
    # of text labels — far more readable, and the ports satisfy ERC.
    stats = cec_sch.build_schematic(out, base, parts, nets, used, LIBS, paper="A3",
                                    power_ports={"GND": "GND", "+5VSB": "+5VSB", "+3V3": "+3V3"},
                                    nc_skip=nc_skip, placement=layout(dirn, parts))
    print(f"modules/{dirn}/{base}.kicad_sch  " +
          "  ".join(f"{k}={v}" for k, v in stats.items() if k != "root") +
          f"  rails={len(RAILS[dirn])}")
