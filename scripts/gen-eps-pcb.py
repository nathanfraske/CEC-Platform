#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Initial floorplan generator for the EPS 8-pin module PCB. Emits a KiCad 10
# .kicad_pcb with: a 4-layer stackup (2oz outer / 1oz inner; In1=GND, In2=12V
# power plane), an Edge.Cuts outline, and the mechanical anchors PLACED with
# net-tagged pads -- the four Mini-Fit Jr 2x4 cable connectors (IN left / OUT
# right, inline), the RJ-45 Hub jack, the ESP32-S3-MINI-1, the two per-cable
# INA238 + WSK2512 shunts, the CAN transceiver and the LDO -- plus four M3
# chassis-ground mounts and a CEC copper logo on the back.
#
# This is FLOOR-PLANNING, not routing: parts are positioned, nets attached;
# copper pours and tracks are drawn in the GUI. The discrete decoupling/bias
# passives are intentionally left for "Update PCB from Schematic" to pull in.
#
#   python3 scripts/gen-eps-pcb.py   # writes modules/eps-8pin/eps8pin-module.kicad_pcb
# Verify: kicad-cli pcb render / kicad-cli pcb drc
import os, re, sys, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NET  = f"{ROOT}/modules/eps-8pin/eps8pin-module.net"
OUT  = f"{ROOT}/modules/eps-8pin/eps8pin-module.kicad_pcb"

# ---- board ----
W, H = 72.0, 62.0                      # board outline (mm)
# Placement: refdes -> (pad-1 origin x, y, rotation). Inline power path: the two
# PSU-side IN connectors mate at the TOP edge (rot 0), the two load-side OUT at
# the BOTTOM edge (rot 180), so 12V flows top->bottom through each cable's shunt;
# cables sit on the left two-thirds, the RJ-45 Hub jack takes the right edge, and
# the ESP (rotated 90 to fit the middle band) + CAN + LDO sit between.
PLACE = {
    "J_IN1":  (8.0, 15.0, 0),    "J_IN2":  (33.0, 15.0, 0),
    "J_OUT1": (20.6, 47.0, 180), "J_OUT2": (45.6, 47.0, 180),
    "RS1": (11.0, 31.0, 0), "U10": (14.5, 25.0, 0),
    "RS2": (42.0, 31.0, 0), "U11": (39.0, 25.0, 0),
    "U1":  (28.0, 31.0, 0),                       # ESP32-S3-MINI-1 (fills the band)
    "U3":  (12.0, 38.0, 0),                       # LP5907 LDO (cable-1 column)
    "U2":  (40.0, 38.0, 0),                       # TJA1462A CAN (cable-2 column)
    "J1":  (63.0, 31.0, 0),                       # RJ-45 to Hub (right edge)
}
# Mounting holes (M3, chassis GND) near the corners, and the back logo centre.
MOUNTS = [(4.0, 4.0), (W - 4.0, 4.0), (4.0, H - 4.0), (W - 4.0, H - 4.0)]
LOGO_AT = (27.0, 31.0)

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

# ---- parse the exported netlist: components (ref->footprint) and nets ----
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
        nodes = [(rr.group(1), pp.group(1)) for rr, pp in
                 ((re.search(r'\(ref "([^"]+)"\)', nb), re.search(r'\(pin "([^"]+)"\)', nb))
                  for nb in (carve(b, mm.start()) for mm in re.finditer(r"\(node\b", b)))
                 if rr and pp]
        nets[nm.group(1)] = nodes
    return comps, nets

comps, nets = parse_netlist(NET)
# net codes (0 reserved for "unconnected"); pad -> (code, name)
names = [n for n in sorted(nets) if n]
code_of = {n: i + 1 for i, n in enumerate(names)}
GND = "GND"
padnet = {(r, p): (code_of[n], n) for n, nodes in nets.items() if n for (r, p) in nodes}

# ---- footprint placement (read .kicad_mod, retarget, set (at), inject nets) ----
def inject_nets(body, ref):
    out, pos = "", 0
    for m in re.finditer(r'\(pad "([^"]*)"', body):
        if m.start() < pos: continue
        blk = carve(body, m.start()); end = m.start() + len(blk)
        out += body[pos:m.start()]
        num = m.group(1); key = (ref, num)
        if num and key in padnet:
            code, name = padnet[key]
            blk = blk[:-1].rstrip() + f'\n\t\t(net {code} "{name}")\n\t)'
        out += blk; pos = end
    return out + body[pos:]

def place(libid, ref, x, y, rot, *, gnd_all=False, flip=False):
    nick, name = libid.split(":")
    s = open(fp_path(nick, name)).read()
    s = s.replace(f'(footprint "{name}"', f'(footprint "{libid}"', 1)
    for k in ("version", "generator", "generator_version"):
        s = re.sub(rf'\n\s*\({k} [^\n]*\)', "", s, count=1)
    # drop any footprint-level uuid that sits right after the layer line
    s = re.sub(r'(\(layer "[^"]+"\))\n\t\(uuid "[^"]+"\)', r"\1", s, count=1)
    if flip:                                   # mirror to the back: swap layers, negate x
        s = re.sub(r'"F\.(Cu|Mask|SilkS|Fab|Paste|Adhes)"', r'"B.\1"', s)
        s = re.sub(r'\(xy (-?[\d.]+) (-?[\d.]+)\)',
                   lambda m: f"(xy {ff(-float(m.group(1)))} {m.group(2)})", s)
    s = re.sub(r'(\(footprint "[^"]+"\n\t\(layer "[^"]+"\))',
               lambda m: m.group(1) + f'\n\t(at {ff(x)} {ff(y)} {rot})\n\t(uuid "{U()}")',
               s, count=1)
    s = re.sub(r'\(property "Reference" "[^"]*"',
               f'(property "Reference" "{ref}"', s, count=1)
    if gnd_all:                                # mounting holes -> chassis GND
        padnet_local = lambda num: (code_of[GND], GND)
        out, pos = "", 0
        for m in re.finditer(r'\(pad "([^"]*)"', s):
            if m.start() < pos: continue
            blk = carve(s, m.start()); end = m.start() + len(blk)
            out += s[pos:m.start()]; num = m.group(1)
            if num:
                code, nm = padnet_local(num)
                blk = blk[:-1].rstrip() + f'\n\t\t(net {code} "{nm}")\n\t)'
            out += blk; pos = end
        s = out + s[pos:]
    else:
        s = inject_nets(s, ref)
    return "\t" + s.strip() + "\n"

# ---- assemble the board ----
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
    # 4-layer, 2oz outer (0.070mm) / 1oz inner (0.035mm). FR4 dielectrics.
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

def edge():
    e = []
    pts = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        e.append(f'\t(gr_line (start {ff(x1)} {ff(y1)}) (end {ff(x2)} {ff(y2)}) '
                 f'(stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "{U()}"))')
    return "\n".join(e)

def silk_note():
    # small board ID on the back silk, tucked under the RJ-45 (clear area)
    return (f'\t(gr_text "CEC EPS-8pin  4L 2oz/1oz" '
            f'(at 63 44 0) (layer "B.SilkS") (uuid "{U()}") '
            f'(effects (font (size 0.8 0.8) (thickness 0.12)) (justify mirror)))')

fps = []
for ref, (x, y, rot) in PLACE.items():
    libid = comps.get(ref)
    if not libid:
        print(f"  WARN no footprint for {ref}", file=sys.stderr); continue
    fps.append(place(libid, ref, x, y, rot))
for i, (x, y) in enumerate(MOUNTS, 1):
    fps.append(place("cec-MountingHole:MountingHole_3.2mm_M3_Pad_Via",
                     f"H{i}", x, y, 0, gnd_all=True))
fps.append(place("cec:CEC_Logo_Copper", "LOGO1", *LOGO_AT, 0, flip=True))

netdecl = '\t(net 0 "")\n' + "\n".join(
    f'\t(net {code_of[n]} "{n}")' for n in names)

doc = ("(kicad_pcb\n\t(version 20260206)\n\t(generator \"cec-gen-eps-pcb\")\n"
       "\t(generator_version \"10.0\")\n"
       "\t(general\n\t\t(thickness 1.6)\n\t\t(legacy_teardrops no)\n\t)\n"
       "\t(paper \"A4\")\n" + LAYERS + "\n\t(setup\n" + stackup() +
       "\n\t\t(pad_to_mask_clearance 0)\n"
       "\t\t(allow_soldermask_bridges_in_footprints no)\n\t)\n"
       + netdecl + "\n" + "\n".join(fps) + "\n" + edge() + "\n"
       + silk_note() + "\n\t(embedded_fonts no)\n)\n")
open(OUT, "w").write(doc)
print(f"wrote {os.path.relpath(OUT, ROOT)}  "
      f"footprints={len(fps)} nets={len(names)} board={W}x{H}mm")
