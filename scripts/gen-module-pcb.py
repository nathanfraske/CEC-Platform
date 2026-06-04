#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Initial-floorplan generator for the i2c-cable interposer module PCBs (EPS and
# the two PCIe SKUs). Parametric in the cable count N: N PSU-side IN connectors
# on the top edge (rot 0) and N load-side OUT on the bottom (rot 180) — 12V flows
# top->bottom through each cable's 2-pad R_2512 shunt + INA238 — with the cables
# horizontally inset so the four corner M3 mounts stay clear of the connectors;
# the control/power core (ESP, CAN, LDO) and the flash/debug front end (USB-C,
# BOOT/RESET, ORing diode + CC) + the RJ-45 fill the right. 4-layer, 2oz outer /
# 1oz inner (In1=GND, In2=12V). CEC copper logo on the back.
#
# ONE-SHOT bootstrap: once a .kicad_pcb is opened/edited in the GUI it is
# hand-maintained; do NOT re-run this over GUI work.
#   python3 scripts/gen-module-pcb.py    (reads each board's exported .net)
# Verify: kicad-cli pcb render / drc
import os, re, sys, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (module dir, board base name, N cables)
BOARDS = [
    ("eps-8pin",        "eps8pin-module",        2),
    ("pcie-8pin-2port", "pcie8pin-2port-module", 2),
    ("pcie-8pin-3port", "pcie8pin-3port-module", 3),
]
CX0, PITCH = 20.0, 27.0          # first cable origin x, cable pitch (mm)

def geometry(n):
    cables_right = CX0 + (n - 1) * PITCH + 18.7      # rightmost connector courtyard
    ex = cables_right + 4.0                           # electronics region left x
    return ex + 36.0, 66.0, ex                        # W, H, ex

def placement(n):
    W, H, ex = geometry(n)
    P = {}
    for i in range(n):                                # cables, left to right
        x, c = CX0 + i * PITCH, i + 1
        P[f"J_IN{c}"]  = (x, 17.0, 0)
        P[f"J_OUT{c}"] = (x + 12.6, 49.0, 180)        # pins align under the IN row
        P[f"RS{c}"]    = (x + 3.0, 35.0, 0)           # shunt, mid-gap in the 12V column
        P[f"U1{i}"]    = (x + 9.0, 30.0, 0)           # INA238 (U10, U11, U12)
    P.update({                                        # control/power + flash, right
        "U1":  (ex + 11.0, 33.0, 0),                  # ESP32-S3-MINI-1 (centre band)
        "D2":  (ex + 5.0, 14.0, 0), "C9": (ex + 10.0, 14.0, 0),    # VBUS ORing + bulk (top)
        "U2":  (ex + 16.0, 14.0, 0),                  # TJA1462A CAN (top)
        "J5":  (ex + 28.0, 16.0, 0),                  # USB-C, right edge upper
        "R8":  (ex + 21.0, 26.0, 0), "R9": (ex + 21.0, 32.0, 0),   # CC pulldowns (right of ESP)
        "SW1": (ex + 5.0, 51.0, 0), "SW2": (ex + 13.0, 51.0, 0),   # BOOT / RESET (bottom)
        "U3":  (ex + 21.0, 51.0, 0),                  # LP5907 LDO (bottom)
        "J1":  (ex + 28.0, 44.0, 0),                  # RJ-45, right edge lower-mid
    })
    mounts = [(7.0, 7.0), (W - 7.0, 7.0), (7.0, H - 7.0), (W - 7.0, H - 7.0)]
    logo = (CX0 + (n - 1) * PITCH / 2.0 + 6.3, H / 2.0)
    return W, H, P, mounts, logo

# ---------------------------------------------------------------- helpers
def ff(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s
def U(): return str(uuid.uuid4())

def carve(s, i):
    d = 0; j = i; ins = esc = False
    while j < len(s):
        c = s[j]
        if ins:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': ins = False
        else:
            if c == '"': ins = True
            elif c == "(": d += 1
            elif c == ")":
                d -= 1
                if d == 0: return s[i:j + 1]
        j += 1

def fp_path(nick, name):
    if nick == "cec": return f"{ROOT}/lib/cec.pretty/{name}.kicad_mod"
    if nick.startswith("cec-"): return f"{ROOT}/lib/vendor/{nick[4:]}.pretty/{name}.kicad_mod"
    raise SystemExit(f"unknown footprint lib nickname: {nick}")

def parse_netlist(path):
    s = open(path).read()
    comps, nets = {}, {}
    for m in re.finditer(r"\(comp\b", s):
        b = carve(s, m.start())
        r = re.search(r'\(ref "([^"]+)"', b); fp = re.search(r'\(footprint "([^"]*)"', b)
        if r: comps[r.group(1)] = fp.group(1) if fp else ""
    for m in re.finditer(r"\(net\b", s):
        b = carve(s, m.start())
        nm = re.search(r'\(name "([^"]*)"\)', b)
        if not nm: continue
        nodes = [(rr.group(1), pp.group(1)) for nb in (carve(b, mm.start()) for mm in re.finditer(r"\(node\b", b))
                 for rr, pp in [(re.search(r'\(ref "([^"]+)"\)', nb), re.search(r'\(pin "([^"]+)"\)', nb))] if rr and pp]
        nets[nm.group(1)] = nodes
    return comps, nets

LAYERS = """\t(layers
\t\t(0 "F.Cu" signal)
\t\t(4 "In1.Cu" signal "GND")
\t\t(6 "In2.Cu" power "12V")
\t\t(2 "B.Cu" signal)
\t\t(9 "F.Adhes" user "F.Adhesive")
\t\t(11 "B.Adhes" user "B.Adhesive")
\t\t(13 "F.Paste" user)
\t\t(15 "B.Paste" user)
\t\t(5 "F.SilkS" user "F.Silkscreen")
\t\t(7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user)
\t\t(3 "B.Mask" user)
\t\t(17 "Dwgs.User" user "User.Drawings")
\t\t(19 "Cmts.User" user "User.Comments")
\t\t(21 "Eco1.User" user "User.Eco1")
\t\t(23 "Eco2.User" user "User.Eco2")
\t\t(25 "Edge.Cuts" user)
\t\t(27 "Margin" user)
\t\t(31 "F.CrtYd" user "F.Courtyard")
\t\t(29 "B.CrtYd" user "B.Courtyard")
\t\t(35 "F.Fab" user)
\t\t(33 "B.Fab" user)
\t)"""

def stackup():
    def cu(n, t): return f'\t\t\t(layer "{n}" (type "copper") (thickness {t}))'
    def di(n, t): return (f'\t\t\t(layer "{n}" (type "core") (thickness {t}) '
                          f'(material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))')
    return ("\t\t(stackup\n"
            '\t\t\t(layer "F.SilkS" (type "Top Silk Screen"))\n'
            '\t\t\t(layer "F.Paste" (type "Top Solder Paste"))\n'
            '\t\t\t(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))\n'
            + cu("F.Cu", 0.07) + "\n" + di("dielectric 1", 0.2) + "\n"
            + cu("In1.Cu", 0.035) + "\n" + di("dielectric 2", 1.065) + "\n"
            + cu("In2.Cu", 0.035) + "\n" + di("dielectric 3", 0.2) + "\n"
            + cu("B.Cu", 0.07) + "\n"
            '\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))\n'
            '\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))\n'
            '\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen"))\n'
            '\t\t\t(copper_finish "ENIG")\n\t\t\t(dielectric_constraints no)\n\t\t)')

def place(libid, ref, x, y, rot, padnet, code_of, *, gnd_all=False, flip=False):
    nick, name = libid.split(":")
    s = open(fp_path(nick, name)).read()
    s = s.replace(f'(footprint "{name}"', f'(footprint "{libid}"', 1)
    for k in ("version", "generator", "generator_version"):
        s = re.sub(rf'\n\s*\({k} [^\n]*\)', "", s, count=1)
    s = re.sub(r'(\(layer "[^"]+"\))\n\t\(uuid "[^"]+"\)', r"\1", s, count=1)
    if flip:
        s = re.sub(r'"F\.(Cu|Mask|SilkS|Fab|Paste|Adhes)"', r'"B.\1"', s)
        s = re.sub(r'\(xy (-?[\d.]+) (-?[\d.]+)\)',
                   lambda m: f"(xy {ff(-float(m.group(1)))} {m.group(2)})", s)
    s = re.sub(r'(\(footprint "[^"]+"\n\t\(layer "[^"]+"\))',
               lambda m: m.group(1) + f'\n\t(at {ff(x)} {ff(y)} {rot})\n\t(uuid "{U()}")', s, count=1)
    s = re.sub(r'\(property "Reference" "[^"]*"', f'(property "Reference" "{ref}"', s, count=1)
    out, pos = "", 0
    for m in re.finditer(r'\(pad "([^"]*)"', s):
        if m.start() < pos: continue
        blk = carve(s, m.start()); end = m.start() + len(blk); out += s[pos:m.start()]
        num = m.group(1); tag = None
        if gnd_all and num:
            tag = (code_of["GND"], "GND")
        elif num and (ref, num) in padnet:
            tag = padnet[(ref, num)]
        if tag:
            blk = blk[:-1].rstrip() + f'\n\t\t(net {tag[0]} "{tag[1]}")\n\t)'
        out += blk; pos = end
    return "\t" + (out + s[pos:]).strip() + "\n"

def build(dir_, base, n):
    netf = f"{ROOT}/modules/{dir_}/{base}.net"
    comps, nets = parse_netlist(netf)
    names = [x for x in sorted(nets) if x]
    code_of = {x: i + 1 for i, x in enumerate(names)}
    padnet = {(r, p): (code_of[x], x) for x, nodes in nets.items() if x for (r, p) in nodes}
    W, H, P, mounts, logo = placement(n)

    fps = []
    for ref, (x, y, rot) in P.items():
        lib = comps.get(ref)
        if lib: fps.append(place(lib, ref, x, y, rot, padnet, code_of))
        else: print(f"  WARN no footprint for {ref} in {base}", file=sys.stderr)
    for i, (x, y) in enumerate(mounts, 1):
        fps.append(place("cec-MountingHole:MountingHole_3.2mm_M3_Pad_Via",
                         f"H{i}", x, y, 0, padnet, code_of, gnd_all=True))
    fps.append(place("cec:CEC_Logo_Copper", "LOGO1", logo[0], logo[1], 0, padnet, code_of, flip=True))

    e = []
    pts = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        e.append(f'\t(gr_line (start {ff(x1)} {ff(y1)}) (end {ff(x2)} {ff(y2)}) '
                 f'(stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "{U()}"))')
    note = (f'\t(gr_text "CEC {base}  4L 2oz/1oz" (at {ff(logo[0])} {ff(H - 4)} 0) '
            f'(layer "B.SilkS") (uuid "{U()}") '
            f'(effects (font (size 0.9 0.9) (thickness 0.13)) (justify mirror)))')
    netdecl = '\t(net 0 "")\n' + "\n".join(f'\t(net {code_of[x]} "{x}")' for x in names)
    doc = ("(kicad_pcb\n\t(version 20260206)\n\t(generator \"cec-gen-module-pcb\")\n"
           "\t(generator_version \"10.0\")\n"
           "\t(general\n\t\t(thickness 1.6)\n\t\t(legacy_teardrops no)\n\t)\n"
           "\t(paper \"A4\")\n" + LAYERS + "\n\t(setup\n" + stackup() +
           "\n\t\t(pad_to_mask_clearance 0)\n"
           "\t\t(allow_soldermask_bridges_in_footprints no)\n\t)\n"
           + netdecl + "\n" + "\n".join(fps) + "\n" + "\n".join(e) + "\n"
           + note + "\n\t(embedded_fonts no)\n)\n")
    out = f"{ROOT}/modules/{dir_}/{base}.kicad_pcb"
    open(out, "w").write(doc)
    print(f"{os.path.relpath(out, ROOT)}  N={n} footprints={len(fps)} board={W:.0f}x{H:.0f}mm")

for d, b, n in BOARDS:
    build(d, b, n)
