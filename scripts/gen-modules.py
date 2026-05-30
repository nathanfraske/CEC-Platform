#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Generate the Standard-tier module schematics (24-pin ATX, EPS 8-pin, PCIe
# 8-pin, 12VHPWR Standard). Shared control/comms/power backbone locked to the
# ESP32-S3-MINI-1, plus per-rail sensing: one INA238 (16-bit I2C current/voltage
# monitor, locked for Standard) per sensed rail — high-side shunt across IN+/IN-,
# bus voltage sensed at IN-, on a shared I2C bus to the ESP32. The 24-pin module
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
# LP5907MFX-1.2 body -> -3.3, INA237 body -> INA238.
import re, uuid, os

ROOTDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBS = {"cec": open(f"{ROOTDIR}/lib/cec.kicad_sym").read(),
        "cec-vendor": open(f"{ROOTDIR}/lib/vendor/cec-vendor.kicad_sym").read()}
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

def extract(t, n):
    k = f'(symbol "{n}"'; i = t.find(k)
    if i < 0: raise SystemExit(f"symbol not found: {n}")
    d = 0; ins = esc = False; j = i
    while j < len(t):
        c = t[j]
        if ins:
            if esc: esc = False
            elif c == '\\': esc = True
            elif c == '"': ins = False
        else:
            if c == '"': ins = True
            elif c == '(': d += 1
            elif c == ')':
                d -= 1
                if d == 0: return t[i:j+1]
        j += 1
    raise SystemExit(f"unbalanced: {n}")

def parse_pins(block):
    pins = {}
    for m in re.finditer(r'\(pin\b.*?\(number "([^"]+)"', block, re.S):
        seg = block[m.start():m.end()]
        at = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\)', seg)
        if at: pins[m.group(1)] = (float(at.group(1)), float(at.group(2)))
    return pins

def f(x):
    s = f"{x:.2f}".rstrip("0").rstrip("."); return "0" if s in ("", "-0") else s
def u(): return str(uuid.uuid4())

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
        parts[f"U1{i}"] = ("cec-vendor", "INA237", "INA238")     # INA237 body = INA238 pinout
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
        nets[f"RAIL{rn}_HI"] = [(sh,"1"), (ina,"1")]      # PSU side, IN+
        nets[f"RAIL{rn}_LO"] = [(sh,"2"), (ina,"2")]      # load side, IN- (bus V)
        nets["+3V3"]  += [(ina,"4"), (dec,"1")]           # VS + decoupling
        nets["GND"]   += [(ina,"3"), (ina,"6"), (dec,"2")]
        nets["I2C_SDA"] += [(ina,"8")]
        nets["I2C_SCL"] += [(ina,"7")]
        a0, a1 = STRAP[i]
        nets[a0] += [(ina,"10")]   # A0
        nets[a1] += [(ina,"9")]    # A1
        # ALERT (pin 5) left open in the draft
    if dirn == "atx-24pin":
        nets["+5VSB"] += [("J2","1")]
        nets["GND"]   += [("J2","2")]
    return parts, nets

# load every symbol used across all modules
used = {}
for dirn, _ in MODS:
    for lib, name, _ in build(dirn)[0].values():
        if (lib, name) not in used:
            blk = extract(LIBS[lib], name); used[(lib, name)] = {"block": blk, "pins": parse_pins(blk)}

def extent(p):
    xs = [v[0] for v in p.values()]; ys = [v[1] for v in p.values()]
    return (max(xs)-min(xs) if xs else 0, max(ys)-min(ys) if ys else 0)
cw = max(extent(s["pins"])[0] for s in used.values()) + 38.1
ch = max(extent(s["pins"])[1] for s in used.values()) + 38.1

def embed(lib, name, blk):
    return "\t" + blk.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1).replace("\n", "\n\t")

for dirn, base in MODS:
    parts, nets = build(dirn)
    # guard: no pin in two nets
    seen = {}
    for net, conns in nets.items():
        for c in conns:
            if c in seen: raise SystemExit(f"[{dirn}] pin {c} in two nets: {seen[c]} and {net}")
            seen[c] = net
    out = f"{ROOTDIR}/modules/{dirn}/{base}.kicad_sch"
    root = re.search(r'\(uuid\s+"?([0-9a-fA-F-]+)"?\s*\)', open(out).read()).group(1)
    placement = {r: (50.8 + (i % 6) * cw, 38.1 + (i // 6) * ch) for i, r in enumerate(parts)}
    libset = {(l, n) for (l, n, _) in parts.values()}
    lib_syms = "\t(lib_symbols\n" + "\n".join(embed(l, n, used[(l, n)]["block"]) for (l, n) in libset) + "\n\t)"
    insts = []
    for ref, (lib, name, val) in parts.items():
        x, y = placement[ref]
        pinblk = "\n".join(f'\t\t(pin "{num}" (uuid {u()}))' for num in used[(lib, name)]["pins"])
        insts.append(
            "\t(symbol\n" f'\t\t(lib_id "{lib}:{name}")\n'
            f"\t\t(at {f(x)} {f(y)} 0)\n\t\t(unit 1)\n"
            "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n\t\t(fields_autoplaced yes)\n"
            f"\t\t(uuid {u()})\n"
            f'\t\t(property "Reference" "{ref}" (at {f(x)} {f(y-2.54)} 0) (effects (font (size 1.27 1.27))))\n'
            f'\t\t(property "Value" "{val}" (at {f(x)} {f(y+2.54)} 0) (effects (font (size 1.27 1.27))))\n'
            f'\t\t(property "Footprint" "" (at {f(x)} {f(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
            f'\t\t(property "Datasheet" "" (at {f(x)} {f(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
            f"{pinblk}\n"
            f'\t\t(instances\n\t\t\t(project "{base}"\n\t\t\t\t(path "/{root}" (reference "{ref}") (unit 1))\n\t\t\t)\n\t\t)\n\t)')
    labels = []
    for net, conns in nets.items():
        for ref, pin in conns:
            lib, name, _ = parts[ref]
            lx, ly = used[(lib, name)]["pins"][pin]
            labels.append(f'\t(label "{net}" (at {f(placement[ref][0]+lx)} {f(placement[ref][1]-ly)} 0) (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid {u()}))')
    content = ("(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
        f"\t(uuid {root})\n\t(paper \"A3\")\n{lib_syms}\n" + "\n".join(insts) + "\n" + "\n".join(labels) + "\n"
        "\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n")
    open(out, "w").write(content)
    print(f"modules/{dirn}/{base}.kicad_sch  parts={len(parts)} nets={len(nets)} labels={len(labels)} rails={len(RAILS[dirn])}")
