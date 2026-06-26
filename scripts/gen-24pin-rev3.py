#!/usr/bin/env python3
"""Generate the atx-24pin REV3 schematic in LABELLED FUNCTIONAL SECTIONS.

Reuses gen-modules.build('atx-24pin') for the proven C6 base (ESP32-C6-MINI-1 + 4x INA228 +
CAN + LDO + flash/USB + FTP RJ-45 + DETECT poke-ack, with CAN_H/L names + the PESD ESD diode)
and layers on the rev3 deltas:
  - ATX power path: J3/J4 (CEC_ATX_24) interposer, rail pinout extracted from rev2.
  - J1.1 left OPEN (spec 2.7 v3.3) -- RJ-45 VCC no longer parallels the bulk feed.
  - 5V/5VSB power MUX (TPS2121): IN1=main 5V (post-shunt) priority > IN2=+5VSB -> +5V_SYS; the
    board's own supply (LDO/CAN/flash-OR) moves from +5VSB to +5V_SYS.
  - 6.13 fast transient front-end (INA181 + TLV7011 + shared threshold) on the 12V & 5V rails.
  - 16-pin vertical MEZZANINE connector (CEC_MEZZANINE_16P) for the stacked Hub.
Everything is grouped inside cec_sch labelled-section boxes so the sheet reads by function.

NOTE (TPS2121 control pins): VERIFIED vs the TPS2121RUXR datasheet (SLVSDU5, 2026-06-24 pinout
audit). PR1 = a divider off IN1 (IN1>IN2 priority); OV1/OV2 -> GND (OV disabled); CP2 -> GND
(fast-switchover off); ILIM = R_ILIM 20k to GND (~3.5A, sized to the max running draw per the
2026-06-24 audit); SS = C_SS to GND; ST = 10k pull-up to +3V3. All 7 placed-IC symbol pinouts
were datasheet-verified the same day (C6/INA228/INA181/TLV7011/TPS2121/LP5907/TJA1051 = match).
"""
import sys, os, importlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
gm = importlib.import_module("gen-modules")
import cec_sch

ROOT = os.path.dirname(HERE)
OUT = f"{ROOT}/modules/atx-24pin-rev3/24pin-module.kicad_sch"
BASE = "24pin-module"

parts, nets = gm.build("atx-24pin")          # C6 base + 4x INA228 + flash + CAN + LDO + RJ-45 + poke-ack

def drop(net, conn):
    nets[net] = [c for c in nets[net] if c != conn]

# ---------------------------------------------------------------- delta 1: J1.1 OPEN
drop("+5VSB", ("J1", "1"))                    # RJ-45 VCC no longer fed (spec 2.7 v3.3)

# ---------------------------------------------------------------- delta 2: ATX power path J3/J4
parts["J3"] = ("cec", "CEC_ATX_24", "ATX-24 PSU")
parts["J4"] = ("cec", "CEC_ATX_24", "ATX-24 MB")
RAILPINS = {"12V": [10, 11], "5V": [4, 6, 21, 22, 23], "3V3": [1, 2, 12, 13]}   # 5VSB = pin 9
GNDPINS = [3, 5, 7, 15, 17, 18, 19, 24]
PASS = {"PWROK": 8, "PSON": 16, "NEG12V": 14}
for label, pins in RAILPINS.items():
    for p in pins:
        nets[f"SENSE{label}_HI"].append(("J3", str(p)))
        nets[f"SENSE{label}_LO"].append(("J4", str(p)))
for p in GNDPINS:
    nets["GND"] += [("J3", str(p)), ("J4", str(p))]
for sig, p in PASS.items():
    nets[f"ATX_{sig}"] = [("J3", str(p)), ("J4", str(p))]   # straight passthrough, not sensed

# 5VSB: the board's +5VSB IS the 5VSB-rail HI node (J3.9 -> shunt RS4 -> J4.9). Merge SENSE5VSB_HI
# into +5VSB so there's one node, and tie J3.9 / J4.9.
for c in nets.pop("SENSE5VSB_HI"):            # [RS4.1, U13.10]
    nets["+5VSB"].append(c)
nets["+5VSB"].append(("J3", "9"))
nets["SENSE5VSB_LO"].append(("J4", "9"))

# ---------------------------------------------------------------- delta 3: 5V/5VSB power MUX
parts["U5"] = ("cec-vendor", "TPS2121RUXR", "TPS2121RUXR")
parts["C50"] = ("cec-vendor", "C_Small", "2u2")    # SS soft-start
parts["R50"] = ("cec-vendor", "R_Small", "20k")    # ILIM = max running draw (audit 2026-06-24)
parts["R51"] = ("cec-vendor", "R_Small", "10k")    # ST open-drain pull-up (datasheet 6-20k)
parts["R52"] = ("cec-vendor", "R_Small", "100k")   # PR1 divider top (IN1 -> PR1)
parts["R53"] = ("cec-vendor", "R_Small", "33k")    # PR1 divider bottom; IN1 valid threshold ~4.3V
# the board's own supply moves +5VSB -> +5V_SYS (mux output)
for ref, pin in [("U3", "1"), ("U3", "3"), ("C1", "1"), ("C4", "1"), ("C6", "1"), ("U2", "3"), ("D2", "1")]:
    drop("+5VSB", (ref, pin))
    nets.setdefault("+5V_SYS", []).append((ref, pin))
nets["+5VSB"] += [("U5", "2")]                                   # IN2 = +5VSB (standby)
nets["SENSE5V_LO"] += [("U5", "7")]                             # IN1 = main 5V (post-shunt), priority
nets["+5V_SYS"] += [("U5", "1"), ("U5", "8")]                  # OUT (1+8)
nets["GND"] += [("U5", "12"), ("C50", "2"), ("R50", "2")]
nets["SS"] = [("U5", "11"), ("C50", "1")]
nets["ILIM"] = [("U5", "10"), ("R50", "1")]
nets["MUX_ST"] = [("U5", "9"), ("R51", "1")]                    # status (open-drain) -> pull-up
nets["+3V3"] += [("R51", "2")]
# Control pins -- VERIFIED vs TPS2121RUXR datasheet (SLVSDU5, 2026-06-24 pinout audit):
# PR1 must set IN1 PRIORITY = a divider off IN1 so PR1 > VREF (~1.06V) when IN1 valid (Table 9-3);
# tying PR1 to GND would instead select VCOMP "highest-voltage-wins" mode -- WRONG for this mux.
# OV1/OV2 -> GND = overvoltage supervisors disabled (correct); CP2 -> GND = fast-switchover
# external-ref comparator off -> the simple PR1-priority path (correct).
nets["PR1"] = [("U5", "6"), ("R52", "2"), ("R53", "1")]              # PR1 = IN1 divider tap
nets["SENSE5V_LO"] += [("R52", "1")]                                 # divider top -> IN1 (main 5V)
nets["GND"] += [("U5", "4"), ("U5", "5"), ("U5", "3"), ("R53", "2")] # OV2,OV1,CP2 + divider bottom

# ---------------------------------------------------------------- delta 4: 6.13 transient front-end
# On the two high-current rails (12V, 5V). INA181A2 (gain 50) -> TLV7011 comparator vs shared
# firmware threshold (THRESH_PWM IO14 -> RC) -> DET latch into a C6 GPIO. Mirrors gen-modules.
parts["R60"] = ("cec-vendor", "R_Small", "10k")    # PWM->threshold series R
parts["C60"] = ("cec-vendor", "C_Small", "100n")   # PWM->threshold filter C
nets["THRESH_PWM"] = [("U1", "19"), ("R60", "1")]  # IO14 LEDC PWM
nets["THRESH"] = [("R60", "2"), ("C60", "1")]
nets["GND"] += [("C60", "2")]
DET_GPIO = {"12V": "28", "5V": "29"}               # C6 IO22 / IO23
for label in ("12V", "5V"):
    amp, cmp = f"U6{label}", f"U7{label}"
    ca, cb = f"C6{label}", f"C7{label}"
    parts[amp] = ("cec-vendor", "INA181A2IDBVR", "INA181A2IDBVR")
    parts[cmp] = ("cec-vendor", "TLV7011DBVR", "TLV7011DBVR")
    parts[ca] = ("cec-vendor", "C_Small", "100n")
    parts[cb] = ("cec-vendor", "C_Small", "100n")
    nets[f"SENSE{label}_HI"] += [(amp, "3")]        # INA181: 1=OUT 2=GND 3=IN+ 4=IN- 5=REF 6=VS
    nets[f"SENSE{label}_LO"] += [(amp, "4")]
    nets["+3V3"] += [(amp, "6"), (ca, "1"), (cmp, "5"), (cb, "1")]
    nets["GND"] += [(amp, "2"), (amp, "5"), (ca, "2"), (cmp, "2"), (cb, "2")]
    nets[f"DETAMP{label}"] = [(amp, "1"), (cmp, "3")]
    nets["THRESH"] += [(cmp, "4")]
    nets[f"DET{label}"] = [(cmp, "1"), ("U1", DET_GPIO[label])]

# ---------------------------------------------------------------- delta 5: MEZZANINE connector
parts["J6"] = ("cec", "CEC_MEZZANINE_16P", "TO-HUB-STACK")
nets["+5V_SYS"] += [("J6", "1"), ("J6", "2"), ("J6", "3")]
nets["GND"] += [("J6", p) for p in ("4", "7", "10", "12", "14", "15", "16")]
nets["CAN_H"] += [("J6", "5")]
nets["CAN_L"] += [("J6", "6")]
nets["DETECT"] += [("J6", "11")]
# STREAM_P/N (pins 8/9, Pro-only RS-485) + RSVD (13) unused on Standard -> NC

# the post-shunt 5V (J4 / motherboard side) IS the mux's main-5V input -> give it a power-rail
# identity (+5V_MAIN) so ERC sees a real PSU-fed rail (flagged below), not an undriven sense net.
nets["+5V_MAIN"] = nets.pop("SENSE5V_LO")

# ---------------------------------------------------------------- generate
nc_skip = set()    # all open pins (J1.1 open, U1.4 NC, J6.8/9/13 unused, J3/J4.20, USB SBU) get NC flags
used = cec_sch.load_symbols(gm.LIBS, parts)
fps = {r: gm.footprint_for(r, *parts[r]) for r in parts}
fps["J3"] = fps["J4"] = "cec-Connector_Molex:Molex_Mini-Fit_Jr_5569-24A2_2x12_P4.20mm_Horizontal"
fps["J6"] = "cec-Connector_PinHeader_2.00mm:PinHeader_2x08_P2.00mm_Vertical"
fps["U5"] = "cec-vendor:RUX0012A"
wire_nets = [f"SENSE{label}_HI" for label in ("12V", "5V", "3V3")]

# ---- LABELLED SECTIONS + placement (group each cluster inside its box) ----
SECTIONS = {
    "ATX POWER PATH (interposer)":      (20, 24, 130, 150),
    "RAIL SENSING  4x INA228":          (134, 24, 250, 150),
    "6.13 TRANSIENT DETECTION (12V/5V)": (254, 24, 405, 150),
    "5V / 5VSB POWER MUX  TPS2121":     (20, 156, 135, 250),
    "3V3 LDO":                          (139, 156, 205, 250),
    "MCU  ESP32-C6-MINI-1":             (209, 156, 300, 252),
    "CAN  TJA1051":                     (304, 156, 378, 250),
    "FLASH / USB-C":                    (20, 256, 150, 293),
    "HUB LINK  RJ-45 + DETECT":         (160, 256, 262, 293),
    "MEZZANINE  (stacked Hub)":         (270, 256, 360, 293),
}
P = {
    # ATX power path
    "J3": (45, 55), "J4": (45, 120), "RS1": (95, 70), "RS2": (95, 88), "RS3": (95, 106), "RS4": (110, 124),
    # rail sensing (INA228 U10..U13 + decoupling C10..C13)
    "U10": (160, 55), "U11": (160, 85), "U12": (160, 115), "U13": (210, 55),
    "C10": (185, 55), "C11": (185, 85), "C12": (185, 115), "C13": (235, 55),
    "R3": (160, 38), "R4": (180, 38),
    # 6.13
    "U612V": (275, 50), "U712V": (310, 50), "C612V": (293, 50), "C712V": (328, 50),
    "U65V": (275, 95), "U75V": (310, 95), "C65V": (293, 95), "C75V": (328, 95),
    "R60": (360, 60), "C60": (380, 60),
    # mux
    "U5": (60, 200), "C50": (30, 235), "R50": (50, 235), "R51": (95, 235), "C1": (118, 175), "C6": (30, 175),
    "R52": (112, 215), "R53": (112, 232),
    # LDO
    "U3": (165, 195), "C2": (190, 175),
    # MCU
    "U1": (250, 205), "C3": (215, 245), "C7": (290, 245),
    # CAN
    "U2": (335, 195), "C4": (310, 170), "C8": (365, 240),
    # flash / usb
    "J5": (45, 275), "D2": (90, 268), "C9": (110, 268), "R8": (125, 285), "R9": (140, 285),
    "SW1": (70, 290), "SW2": (95, 290),
    # hub link
    "J1": (180, 275), "R1": (215, 285), "D1": (235, 285), "R7": (215, 268), "R2": (245, 285),
    "C5": (255, 268), "J2": (160, 290),
    # mezzanine
    "J6": (310, 278),
}

# power_ports / powerflag for the flat AND the hierarchical generators
POWER_PORTS = {"GND": "GND", "+5VSB": "+5VSB", "+3V3": "+3V3", "+5V_SYS": "+5V_SYS", "+5V_MAIN": "+5V_MAIN"}
POWERFLAG = ["+5VSB", "+5V_SYS", "+5V_MAIN", "GND"]

if __name__ == "__main__":   # importing this module yields parts/nets/used WITHOUT writing anything
    import sys
    if "--flat" in sys.argv:                                  # legacy single-sheet sectioned form
        stats = cec_sch.build_schematic(
            OUT, BASE, parts, nets, used, gm.LIBS, paper="A3",
            power_ports=POWER_PORTS, powerflag_nets=POWERFLAG,
            nc_skip=nc_skip, placement=P, wire_nets=wire_nets, footprints=fps, sections=SECTIONS)
        print(f"FLAT {OUT}\n  " + "  ".join(f"{k}={v}" for k, v in stats.items() if k != "root"))
    else:                                                     # DEFAULT: the adopted HIERARCHICAL schematic
        import importlib
        H = importlib.import_module("cec_sch_hier")
        root, _, _ = H.build_hier_from(parts, nets, used, gm.LIBS, BASE,
                                       power_ports=POWER_PORTS, outdir=os.path.dirname(OUT),
                                       root_name=f"{BASE}.kicad_sch")
        rep = H.verify(root, parts, nets)
        print(f"HIERARCHICAL {root}")
        print(f"  verify: matched={rep['matched']}/{rep['flat_nets']} missing_nets={rep['n_missing_nets']}"
              f"  {'PASS' if rep['n_missing_nets'] == 0 else 'FAIL'}")
