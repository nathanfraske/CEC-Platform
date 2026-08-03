#!/usr/bin/env python3
"""Generate the Hub REV2 schematic in LABELLED SECTIONS.

The Hub Standard schematic is hand-maintained + fully BOM-sourced, so this regenerates from its
EXTRACTED netlist (build/hub-rev2/extract.json -- parts/nets/footprints + LCSC/MPN preserved via
cec_sch's props=) and lays the parts out in role-based labelled sections. Rev2 delta: the mezzanine
SOCKET (mirror of the 24-pin rev3 header) wired as "port 0" -- +5V_SYS(pre-muxed) -> +5VSB rail,
the shared CAN bus, /DETECT1, GND. Population variant: J_MEZZ XOR the J2 RJ-45 port.

NOTE: this is the archived sectioned draft
(old-revisions/hubs/hub-rev2-sectioned-draft/), not the current BETA Hub.
hub-standard (which stays the source of truth). Run scripts/gen-hub-extract first if the netlist moved.
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_sch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = json.load(open(f"{ROOT}/old-revisions/hubs/hub-rev2-sectioned-draft/extract.json"))
OUT = f"{ROOT}/old-revisions/hubs/hub-rev2-sectioned-draft/hub-rev2.kicad_sch"
BASE = "hub-rev2"
LIBS = {"cec": open(f"{ROOT}/lib/cec.kicad_sym").read(),
        "cec-vendor": open(f"{ROOT}/lib/vendor/cec-vendor.kicad_sym").read(),
        "power": open(f"{ROOT}/lib/vendor/cec-power.kicad_sym").read()}

comps = EX["comps"]
nets = {k: [tuple(n) for n in v] for k, v in EX["nets"].items() if not k.startswith("unconnected-")}
parts = {r: (c["lib"], c["part"], c["value"]) for r, c in comps.items()}
fps = {r: c["fp"] for r, c in comps.items()}
props = {r: {k: c[k] for k in ("LCSC", "MPN") if c.get(k)} for r, c in comps.items()}

# ---------------- Rev2 delta: mezzanine SOCKET (port-0 mirror) ----------------
parts["J_MEZZ"] = ("cec", "CEC_MEZZANINE_16P", "FROM-24PIN-STACK")
fps["J_MEZZ"] = "cec-Connector_PinSocket_2.00mm:PinSocket_2x08_P2.00mm_Vertical"
nets["+5VSB"] += [("J_MEZZ", "1"), ("J_MEZZ", "2"), ("J_MEZZ", "3")]   # pre-muxed +5V_SYS from the 24-pin
nets["GND"] += [("J_MEZZ", p) for p in ("4", "7", "10", "12", "14", "15", "16")]
nets["/CAN_H"] += [("J_MEZZ", "5")]
nets["/CAN_L"] += [("J_MEZZ", "6")]
nets["/DETECT1"] += [("J_MEZZ", "11")]   # shares port-0's DETECT ADC (J_MEZZ XOR J2)
# J_MEZZ pins 8,9 (STREAM, Pro) + 13 (RSVD) unused on Standard -> NC

# ---------------- role-based sections ----------------
SECT = {  # explicit assignment for ICs / connectors / switches / LEDs
    "U1": "MCU", "U2": "CAN", "U3": "LDO 3V3", "U4": "SUPERVISOR", "U5": "POWER FRONT-END (2.9 mux)",
    "U6": "LED CHAIN", "U7": "POWER FRONT-END (2.9 mux)",
    "J2": "RJ-45 PORTS", "J3": "RJ-45 PORTS", "J4": "RJ-45 PORTS", "J5": "RJ-45 PORTS",
    "J_KVM": "NanoKVM AUX", "J_USB": "USB-C", "J_5V": "POWER FRONT-END (2.9 mux)",
    "J_5VSB": "POWER FRONT-END (2.9 mux)", "J_MEZZ": "MEZZANINE (Rev2)",
    "SW_BOOT": "MCU", "SW_RESET": "MCU", "TH1": "SUPERVISOR",
}
for r in comps:
    if re.match(r"DL\d", r): SECT[r] = "LED CHAIN"
    elif r in ("D1",): SECT[r] = "POWER FRONT-END (2.9 mux)"
    elif re.match(r"D[2-5]$", r): SECT[r] = "RJ-45 PORTS"
    elif r == "D6": SECT[r] = "USB-C"
    elif r == "D7": SECT[r] = "NanoKVM AUX"
# passives: assign to the section of the part they share the most nets with
def part_nets(ref):
    return [n for n, conns in nets.items() for rr, _ in conns if rr == ref]
for r in list(parts):
    if r in SECT: continue
    tally = {}
    shared = set(part_nets(r))
    for other in SECT:
        if other not in parts: continue
        if shared & set(part_nets(other)):
            tally[SECT[other]] = tally.get(SECT[other], 0) + len(shared & set(part_nets(other)))
    SECT[r] = max(tally, key=tally.get) if tally else "MCU"

# ---------------- section boxes (A2) + auto-grid placement ----------------
BOXES = {
    "POWER FRONT-END (2.9 mux)": (16, 20, 250, 200),
    "MCU":                       (256, 20, 410, 230),
    "CAN":                       (416, 20, 540, 120),
    "LDO 3V3":                   (416, 126, 540, 200),
    "SUPERVISOR":                (16, 206, 150, 300),
    "LED CHAIN":                 (156, 236, 410, 320),
    "NanoKVM AUX":               (416, 206, 540, 320),
    "RJ-45 PORTS":               (16, 306, 320, 414),
    "USB-C":                     (326, 326, 430, 414),
    "MEZZANINE (Rev2)":          (436, 326, 540, 414),
}
placement = {}
for label, (x0, y0, x1, y1) in BOXES.items():
    members = [r for r in parts if SECT.get(r) == label]
    members.sort(key=lambda r: (0 if re.match(r"(U|J|SW|DL|TH)", r) else 1, r))
    cols = max(1, int((x1 - x0 - 10) // 33))
    for i, r in enumerate(members):
        placement[r] = (x0 + 12 + (i % cols) * 33, y0 + 22 + (i // cols) * 30)

# ---------------- generate ----------------
used = cec_sch.load_symbols(LIBS, parts)
power_ports = {"GND": "GND", "+5VSB": "+5VSB", "+3V3": "+3V3"}
# the §2.9 cascade rails are connector-fed / TPS2121-outputs (power_input typed) -> need PWR_FLAGs
powerflag_nets = ["+5VSB", "/5VSB_RAW", "/USB_VBUS", "/MAIN_5V_RAW", "/PSU_5V", "/+5V_HOLD", "GND"]
stats = cec_sch.build_schematic(
    OUT, BASE, parts, nets, used, LIBS, paper="A2",
    power_ports=power_ports, powerflag_nets=powerflag_nets,
    placement=placement, footprints=fps, props=props, sections=BOXES)
print(f"{OUT}\n  " + "  ".join(f"{k}={v}" for k, v in stats.items() if k != "root"))
print(f"  parts={len(parts)} nets={len(nets)} sections={len(BOXES)}  unsectioned={[r for r in parts if r not in SECT]}")
