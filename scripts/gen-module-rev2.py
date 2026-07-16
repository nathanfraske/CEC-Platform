#!/usr/bin/env python3
"""Generate a Rev2 of an i2c-cable module (eps-8pin / pcie-8pin-2port / pcie-8pin-3port) in
LABELLED SECTIONS, regenerated from the module's extracted netlist (BOM/LCSC preserved via
cec_sch props=). Same treatment as the Hub Rev2; these modules are already C6 + §6.13 + sourced,
so this is purely the sectioned-layout pass. Run: python3 gen-module-rev2.py <module-name>
"""
import sys, os, re, json, shutil, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_sch

NAME = sys.argv[1] if len(sys.argv) > 1 else "eps-8pin"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = f"{ROOT}/modules/{NAME}"
DST = f"{ROOT}/modules/{NAME}-rev2"
NET = f"{ROOT}/build/mod-rev2/{NAME}.net"
LIBS = {"cec": open(f"{ROOT}/lib/cec.kicad_sym").read(),
        "cec-vendor": open(f"{ROOT}/lib/vendor/cec-vendor.kicad_sym").read(),
        "power": open(f"{ROOT}/lib/vendor/cec-power.kicad_sym").read()}

# ---- scaffold the Rev2 dir ----
os.makedirs(DST, exist_ok=True)
srcsch = [f for f in os.listdir(SRC) if f.endswith(".kicad_sch")][0]
BASE = srcsch[:-10] + "-rev2"
for ext in ("sym-lib-table", "fp-lib-table"):
    if os.path.exists(f"{SRC}/{ext}"): shutil.copy(f"{SRC}/{ext}", f"{DST}/{ext}")
pro = [f for f in os.listdir(SRC) if f.endswith(".kicad_pro")]
if pro: shutil.copy(f"{SRC}/{pro[0]}", f"{DST}/{BASE}.kicad_pro")
OUT = f"{DST}/{BASE}.kicad_sch"
open(OUT, "w").write(f'(kicad_sch (version 20260306) (generator "eeschema") (generator_version "10.0") (uuid "{uuid.uuid4()}") (paper "A2"))\n')
open(f"{DST}/DRAFT", "w").write("DRAFT\n")

# ---- extract (parts/nets/footprints + LCSC/MPN) ----
t = open(NET).read()
comps = {}
for b in re.split(r'\n\t\t\(comp\n', t)[1:]:
    b = b.split('\n\t\t(libparts')[0]
    ref = (re.search(r'\(ref "([^"]+)"\)', b) or [None, ''])[1]
    if not ref: continue
    val = (re.search(r'\(value "([^"]*)"\)', b) or [None, ''])[1]
    fp = (re.search(r'\(footprint "([^"]*)"\)', b) or [None, ''])[1]
    ls = re.search(r'\(libsource\s*\(lib "([^"]*)"\)\s*\(part "([^"]*)"', b)
    def fld(n):
        m = re.search(r'\(name "%s"\)\s*"?([^")\n]*)' % n, b); return (m.group(1).strip() if m else '')
    comps[ref] = {'value': val, 'fp': fp, 'lib': ls.group(1) if ls else '?', 'part': ls.group(2) if ls else '?',
                  'LCSC': fld('LCSC'), 'MPN': fld('MPN')}
nets = {}
for nb in re.split(r'\n\t\t\(net\n', t)[1:]:
    nb = nb.split('\n\t\t(net\n')[0]
    nm = (re.search(r'\(name "([^"]+)"\)', nb) or [None, ''])[1]
    nodes = re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"', nb)
    if nm and not nm.startswith("unconnected-"): nets[nm] = [tuple(n) for n in nodes]
parts = {r: (c['lib'], c['part'], c['value']) for r, c in comps.items()}
fps = {r: c['fp'] for r, c in comps.items()}
props = {r: {k: c[k] for k in ("LCSC", "MPN") if c.get(k)} for r, c in comps.items()}

# ---- role-based sections ----
SECT = {"U1": "MCU  ESP32-C6", "U2": "CAN  TJA1051", "U3": "LDO 3V3",
        "J1": "HUB LINK  RJ-45 + DETECT", "J5": "FLASH / USB-C"}
for r in comps:
    if re.match(r"U1\d", r) or re.match(r"U2\d", r) or re.match(r"U3\d", r) or r.startswith("RS"):
        SECT[r] = "CABLE SENSING  INA238 + shunt + 6.13"
    elif re.match(r"J_(IN|OUT)", r): SECT[r] = "CABLE CONNECTORS (interposer)"
    elif re.match(r"SW", r): SECT[r] = "FLASH / USB-C"
    elif r == "D1": SECT[r] = "HUB LINK  RJ-45 + DETECT"
    elif r == "D2": SECT[r] = "FLASH / USB-C"
    elif r in ("R10", "C40"): SECT[r] = "CABLE SENSING  INA238 + shunt + 6.13"
def part_nets(ref): return [n for n, conns in nets.items() for rr, _ in conns if rr == ref]
for r in list(parts):
    if r in SECT: continue
    tally = {}; shared = set(part_nets(r))
    for other in SECT:
        if other in parts and (shared & set(part_nets(other))):
            tally[SECT[other]] = tally.get(SECT[other], 0) + len(shared & set(part_nets(other)))
    SECT[r] = max(tally, key=tally.get) if tally else "MCU  ESP32-C6"

BOXES = {
    "CABLE CONNECTORS (interposer)":         (16, 20, 220, 130),
    "MCU  ESP32-C6":                         (226, 20, 360, 140),
    "CAN  TJA1051":                          (366, 20, 480, 78),
    "LDO 3V3":                               (366, 84, 480, 140),
    "CABLE SENSING  INA238 + shunt + 6.13":  (16, 146, 480, 318),
    "FLASH / USB-C":                         (16, 324, 240, 414),
    "HUB LINK  RJ-45 + DETECT":              (246, 324, 480, 414),
}
placement = {}
for label, (x0, y0, x1, y1) in BOXES.items():
    members = sorted([r for r in parts if SECT.get(r) == label],
                     key=lambda r: (0 if re.match(r"(U|J|SW)", r) else 1, r))
    cols = max(1, int((x1 - x0 - 10) // 33))
    for i, r in enumerate(members):
        placement[r] = (x0 + 12 + (i % cols) * 33, y0 + 22 + (i // cols) * 30)

used = cec_sch.load_symbols(LIBS, parts)
stats = cec_sch.build_schematic(
    OUT, BASE, parts, nets, used, LIBS, paper="A2",
    power_ports={"GND": "GND", "+5VSB": "+5VSB", "+3V3": "+3V3"},
    powerflag_nets=["+5VSB", "GND"],
    placement=placement, footprints=fps, props=props, sections=BOXES)
json.dump({'comps': comps, 'nets': {k: v for k, v in nets.items()}}, open(f"{DST}/extract.json", "w"))
print(f"{OUT}\n  " + "  ".join(f"{k}={v}" for k, v in stats.items() if k != "root"))
print(f"  parts={len(parts)} nets={len(nets)} sections={len(BOXES)}  unsectioned={[r for r in parts if r not in SECT]}")
