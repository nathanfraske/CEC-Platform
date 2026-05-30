#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Generate the Standard-tier module base schematics (24-pin ATX, EPS 8-pin,
# PCIe 8-pin, 12VHPWR Standard). These share one control/comms/power backbone,
# locked to the ESP32-S3-MINI-1: the RJ-45 Hub interface, the DETECT module-ID
# resistor, 5VSB -> LP5907 -> 3V3, and the TJA1462A CAN transceiver (NO CAN
# termination — that is Hub-only, spec §3.1).
#
# The per-rail SENSING front-end (shunts / current-sense amps / dividers, and
# for the 24-pin module the PSU 5VSB tap + 2-pin power-out to the Hub) is
# module-specific and not yet specified — it is intentionally NOT generated here.
#
#   python3 scripts/gen-modules.py
#
# Hand-authored without kicad-cli; validate with `kicad-cli sch erc`. Symbol
# stand-ins (values labeled as intended parts): TJA1051T-3 for TJA1462A,
# LP5907MFX-1.2 body for the -3.3 variant.
import re, uuid, os

ROOTDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBS = {"cec": open(f"{ROOTDIR}/lib/cec.kicad_sym").read(),
        "cec-vendor": open(f"{ROOTDIR}/lib/vendor/cec-vendor.kicad_sym").read()}
MODS = [("atx-24pin", "24pin-module"), ("eps-8pin", "eps8pin-module"),
        ("pcie-8pin", "pcie8pin-module"), ("12vhpwr-standard", "12vhpwr-standard-module")]

def extract(text, name):
    key = f'(symbol "{name}"'; i = text.find(key)
    if i < 0: raise SystemExit(f"symbol not found: {name}")
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
    raise SystemExit(f"unbalanced: {name}")

def parse_pins(block):
    pins = {}
    for m in re.finditer(r'\(pin\b.*?\(number "([^"]+)"', block, re.S):
        seg = block[m.start():m.end()]
        at = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\)', seg)
        if at: pins[m.group(1)] = (float(at.group(1)), float(at.group(2)))
    return pins

PARTS = {
    "J1": ("cec", "CEC_RJ45_8P8C_FTP", "TO-HUB"),
    "U1": ("cec-vendor", "ESP32-S3-MINI-1", "ESP32-S3-MINI-1-N16R2"),
    "U2": ("cec-vendor", "TJA1051T-3", "TJA1462A"),
    "U3": ("cec-vendor", "LP5907MFX-1.2", "LP5907MFX-3.3"),
    "R1": ("cec-vendor", "R_Small", "R_ID (OQ-6)"),
    "R2": ("cec-vendor", "R_Small", "10k"),
    "C1": ("cec-vendor", "C_Small", "1u"),
    "C2": ("cec-vendor", "C_Small", "1u"),
    "C3": ("cec-vendor", "C_Small", "100n"),
    "C4": ("cec-vendor", "C_Small", "100n"),
    "C5": ("cec-vendor", "C_Small", "100n"),
}
ESP_GND = ["1","2","42","43","46","47","48","49","50","51","52","53","54","55",
           "56","57","58","59","60","61","62","63","64","65"]
NETS = {
    "+5VSB":   [("J1","1"), ("U3","1"), ("U3","3"), ("C1","1"), ("C4","1"), ("U2","3")],
    "+3V3":    [("U3","5"), ("C2","1"), ("C3","1"), ("U1","3"), ("U2","5"), ("R2","1")],
    "GND":     [("J1","2"), ("U3","2"), ("U2","2"), ("U2","8"), ("R1","2"),
                ("C1","2"), ("C2","2"), ("C3","2"), ("C4","2"), ("C5","2")]
               + [("U1", p) for p in ESP_GND],
    "EN":      [("U1","45"), ("R2","2"), ("C5","1")],
    "CAN_TX":  [("U1","21"), ("U2","1")],
    "CAN_RX":  [("U1","22"), ("U2","4")],
    "CAN_H":   [("U2","7"), ("J1","3")],
    "CAN_L":   [("U2","6"), ("J1","6")],
    "DETECT":  [("J1","8"), ("R1","1")],     # module-ID resistor R1 to GND (OQ-6)
    "GPIO0":   [("U1","4")],
}

# guard: no pin in two nets
_seen = {}
for _net, _conns in NETS.items():
    for _c in _conns:
        if _c in _seen: raise SystemExit(f"pin {_c} in two nets: {_seen[_c]} and {_net}")
        _seen[_c] = _net

def f(x):
    s = f"{x:.2f}".rstrip("0").rstrip("."); return "0" if s in ("", "-0") else s
def u(): return str(uuid.uuid4())

used = {}
for lib, name, _ in PARTS.values():
    if (lib, name) not in used:
        blk = extract(LIBS[lib], name); used[(lib, name)] = {"block": blk, "pins": parse_pins(blk)}

def extent(p):
    xs = [v[0] for v in p.values()]; ys = [v[1] for v in p.values()]
    return (max(xs)-min(xs) if xs else 0, max(ys)-min(ys) if ys else 0)
cw = max((extent(s["pins"])[0] for s in used.values()), default=0) + 38.1
ch = max((extent(s["pins"])[1] for s in used.values()), default=0) + 38.1
placement = {r: (50.8 + (i % 5) * cw, 38.1 + (i // 5) * ch) for i, r in enumerate(PARTS)}

def embed(lib, name, blk):
    return "\t" + blk.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1).replace("\n", "\n\t")
lib_syms = "\t(lib_symbols\n" + "\n".join(embed(l, n, s["block"]) for (l, n), s in used.items()) + "\n\t)"

for d, base in MODS:
    out = f"{ROOTDIR}/modules/{d}/{base}.kicad_sch"
    root = re.search(r'\(uuid\s+"?([0-9a-fA-F-]+)"?\s*\)', open(out).read()).group(1)
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
            f'\t\t(instances\n\t\t\t(project "{base}"\n\t\t\t\t(path "/{root}" (reference "{ref}") (unit 1))\n\t\t\t)\n\t\t)\n'
            "\t)")
    labels = []
    for net, conns in NETS.items():
        for ref, pin in conns:
            lib, name, _ = PARTS[ref]
            lx, ly = used[(lib, name)]["pins"][pin]
            px, py = placement[ref][0] + lx, placement[ref][1] - ly
            labels.append(f'\t(label "{net}" (at {f(px)} {f(py)} 0) (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid {u()}))')
    content = (
        "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
        f"\t(uuid {root})\n\t(paper \"A3\")\n"
        f"{lib_syms}\n" + "\n".join(insts) + "\n" + "\n".join(labels) + "\n"
        "\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n")
    open(out, "w").write(content)
    print(f"wrote modules/{d}/{base}.kicad_sch  ({len(content)} B)")
print(f"parts={len(PARTS)} nets={len(NETS)} symbols={len(used)} (sensing front-end NOT generated — module-specific)")
