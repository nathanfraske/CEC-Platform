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
# `kicad-cli sch erc` / open in KiCad 10. Symbol stand-ins: TJA1051T-3 for the
# TJA1462A (same SO-8 CAN pinout), LP5907MFX-1.2 body for the -3.3 variant,
# SB120 body for SS14, TPS3839DBZ for TPS3839K33 — values are labeled as the
# intended parts.
import re, uuid, os

ROOTDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBS = {"cec": open(f"{ROOTDIR}/lib/cec.kicad_sym").read(),
        "cec-vendor": open(f"{ROOTDIR}/lib/vendor/cec-vendor.kicad_sym").read()}
OUT = f"{ROOTDIR}/hubs/hub-standard/hub-standard.kicad_sch"
ROOT = re.search(r'\(uuid\s+"?([0-9a-fA-F-]+)"?\s*\)', open(OUT).read()).group(1)

def extract(text, name):
    key = f'(symbol "{name}"'
    i = text.find(key)
    if i < 0:
        raise SystemExit(f"symbol not found: {name}")
    d = 0; instr = esc = False; j = i
    while j < len(text):
        c = text[j]
        if instr:
            if esc: esc = False
            elif c == '\\': esc = True
            elif c == '"': instr = False
        else:
            if c == '"': instr = True
            elif c == '(': d += 1
            elif c == ')':
                d -= 1
                if d == 0: return text[i:j+1]
        j += 1
    raise SystemExit(f"unbalanced symbol: {name}")

def parse_pins(block):
    pins = {}
    for m in re.finditer(r'\(pin\b.*?\(number "([^"]+)"', block, re.S):
        seg = block[m.start():m.end()]
        at = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\)', seg)
        if at:
            pins[m.group(1)] = (float(at.group(1)), float(at.group(2)), int(float(at.group(3))))
    return pins

# ---- parts: refdes -> (lib, symbol, value) -------------------------------
PARTS = {
    "J1": ("cec", "CEC_PWR_IN_2P", "5VSB_IN"),
    "J2": ("cec", "CEC_RJ45_8P8C_FTP", "PORT1"),
    "J3": ("cec", "CEC_RJ45_8P8C_FTP", "PORT2"),
    "J4": ("cec", "CEC_RJ45_8P8C_FTP", "PORT3"),
    "J5": ("cec", "CEC_RJ45_8P8C_FTP", "PORT4"),
    "J6": ("cec-vendor", "USB_C_Receptacle_USB2.0_16P", "USB-C"),
    "U1": ("cec-vendor", "ESP32-S3-MINI-1", "ESP32-S3-MINI-1-N16R2"),
    "U2": ("cec-vendor", "TJA1051T-3", "TJA1462A"),
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

# guard: a pin must not be assigned to two nets (would short them)
_seen = {}
for _net, _conns in NETS.items():
    for _c in _conns:
        if _c in _seen:
            raise SystemExit(f"pin {_c} assigned to two nets: {_seen[_c]} and {_net}")
        _seen[_c] = _net

def f(x):
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s
def u():
    return str(uuid.uuid4())

# load symbol blocks + pins for every used symbol
used = {}                       # (lib,name) -> {"block":..,"pins":..}
for lib, name, _ in PARTS.values():
    if (lib, name) not in used:
        blk = extract(LIBS[lib], name)
        used[(lib, name)] = {"block": blk, "pins": parse_pins(blk)}

# grid placement: cell larger than the biggest symbol's pin extent
def extent(pins):
    xs = [p[0] for p in pins.values()]; ys = [p[1] for p in pins.values()]
    return (max(xs)-min(xs) if xs else 0, max(ys)-min(ys) if ys else 0)
cw = max((extent(s["pins"])[0] for s in used.values()), default=0) + 38.1
ch = max((extent(s["pins"])[1] for s in used.values()), default=0) + 38.1
cols = 6
placement = {}
for i, ref in enumerate(PARTS):
    placement[ref] = (50.8 + (i % cols) * cw, 38.1 + (i // cols) * ch)

# lib_symbols: embed each used symbol, namespacing only the parent symbol name
def embed(lib, name, blk):
    return "\t" + blk.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1).replace("\n", "\n\t")
lib_syms = "\t(lib_symbols\n" + "\n".join(embed(l, n, s["block"]) for (l, n), s in used.items()) + "\n\t)"

# placed instances
insts = []
for ref, (lib, name, val) in PARTS.items():
    x, y = placement[ref]
    pinblk = "\n".join(f'\t\t(pin "{num}" (uuid {u()}))' for num in used[(lib, name)]["pins"])
    insts.append(
        "\t(symbol\n"
        f'\t\t(lib_id "{lib}:{name}")\n'
        f"\t\t(at {f(x)} {f(y)} 0)\n\t\t(unit 1)\n"
        "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n"
        "\t\t(fields_autoplaced yes)\n"
        f"\t\t(uuid {u()})\n"
        f'\t\t(property "Reference" "{ref}" (at {f(x)} {f(y-2.54)} 0) (effects (font (size 1.27 1.27))))\n'
        f'\t\t(property "Value" "{val}" (at {f(x)} {f(y+2.54)} 0) (effects (font (size 1.27 1.27))))\n'
        f'\t\t(property "Footprint" "" (at {f(x)} {f(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
        f'\t\t(property "Datasheet" "" (at {f(x)} {f(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
        f"{pinblk}\n"
        f'\t\t(instances\n\t\t\t(project "hub-standard"\n\t\t\t\t(path "/{ROOT}" (reference "{ref}") (unit 1))\n\t\t\t)\n\t\t)\n'
        "\t)")

# net labels at each pin's absolute coordinate
labels = []
missing = []
for net, conns in NETS.items():
    for ref, pin in conns:
        lib, name, _ = PARTS[ref]
        pd = used[(lib, name)]["pins"].get(pin)
        if pd is None:
            missing.append((net, ref, pin)); continue
        lx, ly, _a = pd
        px, py = placement[ref][0] + lx, placement[ref][1] - ly
        labels.append(f'\t(label "{net}" (at {f(px)} {f(py)} 0) (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid {u()}))')

if missing:
    raise SystemExit("ERROR: net references to nonexistent pins:\n" +
                     "\n".join(f"  {n}: {r}.{p}" for n, r, p in missing))

content = (
    "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
    f"\t(uuid {ROOT})\n\t(paper \"A3\")\n"
    f"{lib_syms}\n" + "\n".join(insts) + "\n" + "\n".join(labels) + "\n"
    "\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n")
open(OUT, "w").write(content)
print(f"wrote {os.path.relpath(OUT, ROOTDIR)}  ({len(content)} bytes)")
print(f"  parts={len(PARTS)}  nets={len(NETS)}  labels={len(labels)}  symbols={len(used)}")
