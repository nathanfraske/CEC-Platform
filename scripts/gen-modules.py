#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Generate the Standard-tier module schematics (EPS 8-pin, PCIe 8-pin, 12VHPWR
# Standard; the 24-pin ATX is now hand-maintained, see MODS below). Shared
# control/comms/power backbone locked to the ESP32-S3-MINI-1. Sensing topology is
# per-module, per spec v1.5 §6.1/§6.2 (see the SENSE table):
#   EPS/PCIe   per-CABLE I2C INA238 (high-side shunt across Vin+/Vin-, Vbus on
#              the bus pin, shared I2C to the ESP32); EPS x2, PCIe x3 cables.
#   12VHPWR    per-PIN analog: six INA240 across per-pin shunts into the ESP32-S3
#              ADC, plus a 47k/10k rail-voltage divider; no I2C sensing bus.
# The 24-pin (hand-maintained) uses four INA228 and carries the dedicated 2-pin
# +5VSB power-out to the Hub (OQ-1).
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
# atx-24pin is hand-maintained in eeschema (custom layout/wiring + INA228), so it
# is intentionally NOT regenerated here — running this script must never clobber
# that sheet. Its build()/RAILS entries remain below for reference and parity.
MODS = [("eps-8pin", "eps8pin-module"),
        ("pcie-8pin", "pcie8pin-module"), ("12vhpwr-standard", "12vhpwr-standard-module")]
# Sensing model per module, per spec v1.5 §6.1/§6.2 with §6.4 shunt values.
#   "i2c-rail"  : one INA238/INA228 I2C monitor per sensed node (24-pin per-rail).
#   "i2c-cable" : one INA238 I2C monitor per CABLE (EPS/PCIe per-cable granularity).
#   "analog-pin": one INA240 analog amp per PIN into the ESP32-S3 ADC, no I2C
#                 sensing bus (12VHPWR Standard per-pin), plus a 47k/10k rail
#                 voltage divider into the ADC.
# Each entry is (node-label, shunt value). Shunt values are the §6.4 locked table.
SENSE = {
    "atx-24pin":        ("i2c-rail",  [("12V","2m"), ("5V","2m"), ("3V3","2m"), ("5VSB","25m")]),
    "eps-8pin":         ("i2c-cable", [("C1","0m5"), ("C2","0m5")]),                 # 2 cables
    "pcie-8pin":        ("i2c-cable", [("C1","0m5"), ("C2","0m5"), ("C3","0m5")]),   # up to 3
    "12vhpwr-standard": ("analog-pin",[("P1","1m"), ("P2","1m"), ("P3","1m"),
                                       ("P4","1m"), ("P5","1m"), ("P6","1m")]),      # 6 pins
}
# Back-compat view: list of (label, shunt) per module (used by layout()/wiring).
RAILS = {dirn: nodes for dirn, (_topo, nodes) in SENSE.items()}
# INA238 I2C address strap per monitor index: (A0 net, A1 net). Four codes via
# GND/+3V3 on A0/A1 covers up to 4 monitors on one bus (24-pin and PCIe x3 fit).
STRAP = [("GND","GND"), ("+3V3","GND"), ("GND","+3V3"), ("+3V3","+3V3")]
# ESP32-S3 ADC1 pins (GPIO1..7 = phys 5..11) for the 12VHPWR analog sense chain:
# six INA240 outputs + one rail-voltage divider tap.
ADC_PINS = ["5","6","7","8","9","10","11"]
ESP_GND = ["1","2","42","43","46","47","48","49","50","51","52","53","54","55",
           "56","57","58","59","60","61","62","63","64","65"]

# shared control/comms/power backbone
BASE_PARTS = {
    "J1": ("cec", "CEC_RJ45_8P8C_FTP", "TO-HUB"),
    "U1": ("cec-vendor", "ESP32-S3-MINI-1", "ESP32-S3-MINI-1-N4R2"),
    "U2": ("cec-vendor", "TJA1051T-3", "TJA1462A"),
    "U3": ("cec-vendor", "LP5907MFX-1.2", "LP5907MFX-3.3"),
    # DETECT module-ID precision resistor (pin 8 -> GND), read on the Hub's
    # 10k / 3.3V divider. OQ-6 RESOLVED (spec §2.3 v1.7): these generated modules
    # are all CAN-only Standard -> 2.2k (0.595 V code). Use a 1% precision part.
    "R1": ("cec-vendor", "R_Small", "2k2"),
    "R2": ("cec-vendor", "R_Small", "10k"),
    "R3": ("cec-vendor", "R_Small", "2k2"),   # I2C SDA pull-up
    "R4": ("cec-vendor", "R_Small", "2k2"),   # I2C SCL pull-up
    # Decoupling — matches the hand-maintained 24-pin gold standard's
    # 10uF-bulk / 1uF / 100nF tiering. These sit on the rails here; placing each
    # near its IC (esp. the per-IC 100nF and the 10uF bulk at the ESP32) is the
    # layout (GUI) task.
    "C1": ("cec-vendor", "C_Small", "1u"),    # LP5907 VIN bulk (+5VSB)
    "C2": ("cec-vendor", "C_Small", "1u"),    # LP5907 VOUT bulk (+3V3)
    "C3": ("cec-vendor", "C_Small", "100n"),  # ESP32-S3 3V3 local bypass
    "C4": ("cec-vendor", "C_Small", "100n"),  # TJA1462A VCC (+5VSB) bypass
    "C5": ("cec-vendor", "C_Small", "100n"),  # EN reset RC (with R2)
    "C6": ("cec-vendor", "C_Small", "10u"),   # +5VSB board-entry bulk
    "C7": ("cec-vendor", "C_Small", "10u"),   # +3V3 bulk at the ESP32
    "C8": ("cec-vendor", "C_Small", "100n"),  # TJA1462A VIO (+3V3) bypass
    # DETECT-pin protection + poke-and-ack tap (added platform-wide, v3.2).
    # D1: low-capacitance ESD diode on pin 8 -> GND, LOCKED on every Hub/module
    # for hot-plug insertion ESD on the bare analog input (spec §2.4 v2.0).
    # R7: high-Z sense tap from pin 8 to a spare ADC1 GPIO (IO10) so the module
    # can sense a Hub DETECT-line poke and ack over CAN (spec §2.3 v2.6,
    # poke-and-ack). Tap value and sense method (digital edge vs ADC) are OQ-28
    # working choices. D_Schottky is the body stand-in (value names the real ESD
    # part), per the symbol-standin convention above.
    "D1": ("cec-vendor", "D_Schottky", "PESD5V0S1UL"),
    "R7": ("cec-vendor", "R_Small", "100k"),
}

def footprint_for(ref, lib, name, val):
    """Map a generated part to its vendored KiCad footprint (cec* nicknames).
    Shunts (RS*) take the 4-terminal WSK2512 Kelvin land; ordinary R/C take
    0402/0603/0805 by value. Footprint assignment makes the schematic complete
    for BOM + 'Update PCB from Schematic'."""
    M = {
        "CEC_RJ45_8P8C_FTP": "cec-Connector_RJ:RJ45_Amphenol_54602-x08_Horizontal",
        "ESP32-S3-MINI-1":   "cec-RF_Module:ESP32-S2-MINI-1_NoAntKeepout",
        "TJA1051T-3":        "cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        "LP5907MFX-1.2":     "cec-Package_TO_SOT_SMD:SOT-23-5",
        "INA226":            "cec-Package_SO:VSSOP-10_3x3mm_P0.5mm",
        "INA240":            "cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        "CEC_CONN_2x4":      "cec-Connector_Molex:Molex_Mini-Fit_Jr_5569-08A2_2x04_P4.20mm_Horizontal",
        "D_Schottky":        "cec-Diode_SMD:D_SOD-323",
        "CEC_PWR_IN_2P":     "cec-Connector_JST:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal",
    }
    if name in M:
        return M[name]
    if name == "R_Small":
        # Shunts: honest 2-pad R_2512 land with the four-wire Kelvin sense taps
        # drawn off the terminal copper in layout (§6.8) -- matches the 24-pin
        # gold standard; NOT a 4-terminal WSK2512 land. Final shunt part = OQ-11,
        # high-current land/vertical transition = OQ-10.
        return ("cec-Resistor_SMD:R_2512_6332Metric"
                if ref.startswith("RS") else "cec-Resistor_SMD:R_0402_1005Metric")
    if name == "C_Small":
        return {"10u": "cec-Capacitor_SMD:C_0805_2012Metric",
                "1u":  "cec-Capacitor_SMD:C_0603_1608Metric"}.get(
                    val, "cec-Capacitor_SMD:C_0402_1005Metric")
    return ""

def build(dirn):
    topo, nodes = SENSE[dirn]
    parts = dict(BASE_PARTS)
    if dirn == "atx-24pin":
        parts["J2"] = ("cec", "CEC_PWR_IN_2P", "TO-HUB-PWR")     # OQ-1 5VSB power-out
    nets = {
        "+5VSB": [("J1","1"),("U3","1"),("U3","3"),("C1","1"),("C4","1"),("C6","1"),("U2","3")],
        "+3V3":  [("U3","5"),("C2","1"),("C3","1"),("C7","1"),("C8","1"),("U1","3"),("U2","5"),("R2","1"),("R3","2"),("R4","2")],
        "GND":   [("J1","2"),("U3","2"),("U2","2"),("U2","8"),("R1","2"),("D1","2"),
                  ("C1","2"),("C2","2"),("C3","2"),("C4","2"),("C5","2"),
                  ("C6","2"),("C7","2"),("C8","2")] + [("U1",p) for p in ESP_GND],
        # Reset: ESP32-S3 internal BOD + EN RC only (R2 pull-up to 3V3, C5 to
        # GND); no external supervisor on modules. The TPS3839 is a Hub-only
        # part (aggregator role + blackout/hold-up front-end); a module brownout
        # is a recoverable re-enumerate event, so the internal BOD is enough.
        "EN":     [("U1","45"),("R2","2"),("C5","1")],
        "CAN_TX": [("U1","21"),("U2","1")],
        "CAN_RX": [("U1","22"),("U2","4")],
        "CAN_H":  [("U2","7"),("J1","3")],
        "CAN_L":  [("U2","6"),("J1","6")],
        "DETECT": [("J1","8"),("R1","1"),("D1","1"),("R7","1")],
        "DETECT_SENSE": [("R7","2"),("U1","14")],  # poke-and-ack tap -> IO10 (OQ-28)
        "GPIO0":  [("U1","4")],
    }

    if topo in ("i2c-rail", "i2c-cable"):
        # Digital I2C monitors: INA228 on the 24-pin (20-bit), INA238 elsewhere.
        # One monitor per node (a rail on the 24-pin, a cable on EPS/PCIe). Each
        # senses across its own shunt and reports over the shared I2C bus.
        ina_val = "INA228" if dirn == "atx-24pin" else "INA238"
        nets["I2C_SDA"] = [("U1","12"),("R3","1")]   # IO8
        nets["I2C_SCL"] = [("U1","13"),("R4","1")]   # IO9
        for i, (label, sv) in enumerate(nodes):
            parts[f"U1{i}"] = ("cec-vendor", "INA226", ina_val)  # INA226 body = INA238/228 pinout
            parts[f"RS{i+1}"] = ("cec-vendor", "R_Small", sv)
            parts[f"C1{i}"] = ("cec-vendor", "C_Small", "100n")  # VS decoupling
            ina = f"U1{i}"; sh = f"RS{i+1}"; dec = f"C1{i}"
            nets[f"SENSE{label}_HI"] = [(sh,"1"), (ina,"10")]        # supply side, Vin+
            nets[f"SENSE{label}_LO"] = [(sh,"2"), (ina,"9"), (ina,"8")]  # load side, Vin-/Vbus
            nets["+3V3"] += [(ina,"6"), (dec,"1")]
            nets["GND"]  += [(ina,"7"), (dec,"2")]
            nets["I2C_SDA"] += [(ina,"4")]
            nets["I2C_SCL"] += [(ina,"5")]
            a0, a1 = STRAP[i]
            nets[a0] += [(ina,"2")]    # A0 address strap
            nets[a1] += [(ina,"1")]    # A1 address strap
            # Alert (pin 3) left open in the draft

        # EPS/PCIe per-cable interposer: two 8-pin (2x4) connectors per cable —
        # J_IN_n (PSU side) and J_OUT_n (load side). The cable's 12V pins bundle on
        # each side; PSU-side 12V joins SENSE*_HI (into the shunt), load-side 12V
        # joins SENSE*_LO (out of the shunt). GND pins pass straight through and
        # join the board GND. Pin maps below (CEC_CONN_2x4: odd col 1/3/5/7 left,
        # even col 2/4/6/8 right). EPS 8-pin = 4x12V + 4xGND; PCIe 8-pin = 3x12V +
        # 5xGND (the 3 sense pins are grounded on the cable side).
        if topo == "i2c-cable":
            PINMAP = {
                "eps-8pin":  {"12V": [1,2,3,4],   "GND": [5,6,7,8]},
                "pcie-8pin": {"12V": [1,2,3],     "GND": [4,5,6,7,8]},
            }[dirn]
            for i, (label, sv) in enumerate(nodes):
                jin, jout = f"J_IN{i+1}", f"J_OUT{i+1}"
                parts[jin]  = ("cec", "CEC_CONN_2x4", f"{label} PSU")
                parts[jout] = ("cec", "CEC_CONN_2x4", f"{label} LOAD")
                # 12V: PSU-side pins -> SENSE_HI (into shunt); load-side -> SENSE_LO
                for p in PINMAP["12V"]:
                    nets[f"SENSE{label}_HI"].append((jin, str(p)))
                    nets[f"SENSE{label}_LO"].append((jout, str(p)))
                # GND: straight through, both connectors to board GND
                for p in PINMAP["GND"]:
                    nets["GND"] += [(jin, str(p)), (jout, str(p))]


    elif topo == "analog-pin":
        # 12VHPWR Standard (§6.1): six INA240 per-pin current-sense amps feed the
        # ESP32-S3 ADC directly — no I2C sensing bus. Each INA240 sits across its
        # own 1 mΩ per-pin shunt (high-side, IN+/IN- = pins 8/1), runs from +3V3
        # (V+ = pin6), and drives one ADC1 channel (OUT = pin5). A 47k/10k divider
        # (R5/R6) brings the common 12V rail into the 7th ADC pin.
        # Reference: UNIDIRECTIONAL — both REF1(7) and REF2(3) tied to GND so the
        # output swings 0..Vs for forward (PSU->GPU) current, maximizing ADC range
        # since this connector only sources current. (A bidirectional bias would
        # halve the forward range; revisit only if reverse sensing is wanted. The
        # absolute-accuracy path for this board is OQ-8.)
        for i, (label, sv) in enumerate(nodes):
            amp = f"U1{i}"; sh = f"RS{i+1}"; dec = f"C1{i}"
            parts[amp] = ("cec-vendor", "INA240", "INA240A3")
            parts[sh]  = ("cec-vendor", "R_Small", sv)            # 1 mΩ per-pin shunt
            parts[dec] = ("cec-vendor", "C_Small", "100n")        # V+ decoupling
            # per-pin shunt across IN+ (8, supply) / IN- (1, load)
            nets[f"SENSE{label}_HI"] = [(sh,"1"), (amp,"8")]
            nets[f"SENSE{label}_LO"] = [(sh,"2"), (amp,"1")]
            nets["+3V3"] += [(amp,"6"), (dec,"1")]                # V+ to +3V3
            nets["GND"]  += [(amp,"2"), (amp,"4"), (amp,"3"), (amp,"7"), (dec,"2")]  # GND(2,4) + REF1(7)/REF2(3) to GND
            nets[f"ISENSE{label}"] = [(amp,"5"), ("U1", ADC_PINS[i])]     # OUT -> ADC
        # rail-voltage divider: 12V -> 47k(R5) -> tap -> 10k(R6) -> GND, tap to ADC
        parts["R5"] = ("cec-vendor", "R_Small", "47k")
        parts["R6"] = ("cec-vendor", "R_Small", "10k")
        nets["SENSE_VRAIL_HI"] = [("R5","1")]                     # to 12V rail (interposer)
        nets["VRAIL_DIV"] = [("R5","2"), ("R6","1"), ("U1", ADC_PINS[6])]  # divider tap -> ADC
        nets["GND"] += [("R6","2")]

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
        "U3": (150, 55), "C1": (120, 60), "C2": (180, 60), "C6": (95, 40),
        "R1": (120, 110), "R2": (180, 110), "C5": (210, 110),
        "U2": (240, 70), "C4": (240, 35), "C8": (278, 100),
        "U1": (340, 90),
        "R3": (300, 40), "R4": (320, 40),
        "C3": (340, 155), "C7": (388, 155),
        "D1": (85, 70), "R7": (85, 100),
    }
    if dirn == "atx-24pin":
        P["J2"] = (50, 120)
    # sensing clusters along a lower band: shunt left of the monitor (so the
    # SENSE*_HI link draws as a straight wire onto Vin+/IN+), decoupling cap just
    # right of the monitor. Same layout for INA238/INA228 (i2c) and INA240
    # (analog) — the part bodies differ but the cluster geometry is identical.
    # Cable interposers are wide (an 8-pin IN + 8-pin OUT, ~71 mm of stub span per
    # cluster), so the i2c-cable modules need a wider inter-cluster pitch than the
    # analog per-pin row. At 70 mm the IN of one cable and the OUT of the next
    # overlap, and ERC merges their SENSE nets (multiple_net_names). 100 mm clears
    # it; PCIe's 3rd cable still lands inside the A3 width.
    pitch = 100 if SENSE[dirn][0] == "i2c-cable" else 70
    for i in range(len(RAILS[dirn])):
        X = 70 + i * pitch
        P[f"U1{i}"]   = (X, 210)               # current monitor (INA238/228/240)
        P[f"RS{i+1}"] = (X - 25.4, 215.08)     # shunt; pin1 aligned to Vin+/IN+
        P[f"C1{i}"]   = (X + 22.86, 210)       # supply decoupling, beside the monitor
        # EPS/PCIe per-cable interposer connectors: PSU-side IN left of the shunt
        # cluster, LOAD-side OUT to the right, on a band above the sensing row.
        P[f"J_IN{i+1}"]  = (X - 25.4, 160)     # PSU side
        P[f"J_OUT{i+1}"] = (X + 25.4, 160)     # load side
    if dirn == "12vhpwr-standard":
        # 47k/10k rail-voltage divider, parked below the per-pin row
        P["R5"] = (70, 270); P["R6"] = (95, 270)
    return {r: P[r] for r in parts if r in P}

for dirn, base in MODS:
    parts, nets = build(dirn)
    out = f"{ROOTDIR}/modules/{dirn}/{base}.kicad_sch"
    used = cec_sch.load_symbols(LIBS, parts)
    # GPIO0 is the service-button pad — single-pin label by design, no NC flag.
    nc_skip = {("U1", "4")}
    # Power rails use power-PORT symbols (GND triangle, +5VSB/+3V3 bars) instead
    # of text labels. The per-node shunt->monitor sense link (SENSE*_HI) is a
    # 2-pin colinear net -> draw it as a real wire.
    wire_nets = [f"SENSE{label}_HI" for label, _ in RAILS[dirn]]
    fps = {r: footprint_for(r, *parts[r]) for r in parts}
    stats = cec_sch.build_schematic(out, base, parts, nets, used, LIBS, paper="A3",
                                    power_ports={"GND": "GND", "+5VSB": "+5VSB", "+3V3": "+3V3"},
                                    powerflag_nets=["+5VSB", "GND"],
                                    nc_skip=nc_skip, placement=layout(dirn, parts),
                                    wire_nets=wire_nets, footprints=fps)
    print(f"modules/{dirn}/{base}.kicad_sch  " +
          "  ".join(f"{k}={v}" for k, v in stats.items() if k != "root") +
          f"  nodes={len(RAILS[dirn])} topo={SENSE[dirn][0]}")
