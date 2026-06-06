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
    ("eps-8pin",         "eps8pin-module",          2, "cable"),
    ("pcie-8pin-2port",  "pcie8pin-2port-module",   2, "cable"),
    ("pcie-8pin-3port",  "pcie8pin-3port-module",   3, "cable"),
    ("12vhpwr-standard", "12vhpwr-standard-module", 6, "hpwr"),
]
CX0, PITCH = 9.0, 27.0           # first cable origin x (left margin reclaimed), cable pitch (mm)
# Condensed cable-board layout (2026-06-06). The cable connectors are the REAL Molex
# 45586 right-angle Mini-Fit Jr (verified ECAD land): 4.20mm pitch + 4.20mm rows,
# round 1.85mm-drill pads, and two 3.0mm snap pegs 7.3mm in front of the pad rows;
# its body+mouth run ~14mm to one side. We OVERHANG the body/mouth off the board edge
# (J_IN top, J_OUT bottom) and keep only the pads+pegs on-board. The footprint is
# native mouth-toward-+y, so J_IN is placed rot180 / J_OUT rot0 (see placement()).
# The per-cable sense parts sit SIDE-BY-SIDE in a band at the shunt level instead of
# stacked. 3 M3 mounts: the J_IN/J_OUT courtyards eat the left corners (only the
# mid-height clear band is free) and the RJ-45 sits on the right edge, so USB-C moves
# to the TOP edge to free the two right corners; the RJ-45 mouth ALSO overhangs the
# right edge. ~99 x 44 mm vs the old 110 x 66 (-45% area). N>=3 adds inter-cable mounts.
JIN_Y = 10.0                     # J_IN origin: at rot180 the real Molex 45586 pads land at y10 (row1) / y14.2 (row2, 4.2mm rows) and the snap pegs (native +7.3) at y2.7 (hole 1.2 mm off the top edge); mouth overhangs the top edge
BAND_Y = 22.0                    # sense band center (between the J_IN and J_OUT courtyards)

def geometry(n):
    cables_right = CX0 + (n - 1) * PITCH + 18.7      # rightmost connector courtyard
    ex = cables_right + 4.0                           # electronics region left x
    return ex + 40.3, 44.0, ex                        # W, H, ex (W=99, H=44 — the real 45586 land is compact: 4.2mm rows + shallow courtyard)

def placement(n):
    W, H, ex = geometry(n)
    P = {}
    for i in range(n):                                # cables, left to right
        x, c = CX0 + i * PITCH, i + 1
        # Connectors OVERHANG their edges: J_IN body/mouth hangs off the top, J_OUT
        # off the bottom; pads + the 2 snap pegs stay on-board (the peg is the real
        # limit — it can't overhang). The real Molex 45586 footprint is NATIVE-oriented
        # mouth-toward-+y with pads running -x, so J_IN takes rot180 (mouth -> top edge)
        # and J_OUT rot0 (mouth -> bottom edge); that pair reproduces the same pad x-
        # columns as before (J_IN pad1 at x, J_OUT pad1 at x+12.6) so the 12V pins line
        # up and the existing net map is preserved.
        P[f"J_IN{c}"]  = (x, JIN_Y, 180)
        P[f"J_OUT{c}"] = (x + 12.6, H - JIN_Y, 0)
        # Side-by-side sense band across the column at BAND_Y: the shunt sits
        # VERTICAL (rot90) in the 12V path so current flows top->bottom straight
        # through it; INA238 (cable current; VSSOP-10 ~6.4 mm wide) sits to its left
        # and the §6.13 pair (INA181A2 gain-50 CSA -> TLV7011 comparator) stacks to
        # its right, all Kelvin-tapping the same shunt terminals.
        P[f"U1{i}"]    = (x + 2.0, BAND_Y, 0)         # INA238 (U10, U11, U12)
        P[f"RS{c}"]    = (x + 8.0, BAND_Y, 90)        # 0.5 mOhm shunt, vertical in the 12V path
        P[f"U2{i}"]    = (x + 12.5, BAND_Y - 2.5, 0)  # INA181A2 CSA (U20, U21, U22)
        P[f"U3{i}"]    = (x + 12.5, BAND_Y + 2.5, 0)  # TLV7011 comparator (U30, U31, U32)
    P.update({                                        # control/power + flash, right
        "U1":  (ex + 8.0, 22.0, 0),                   # ESP32-C6-MINI-1 (13x17 crtyd), left column mid
        "U2":  (ex + 19.5, 7.0, 0),                   # TJA1051T/3 CAN (top of mid-strip)
        "U3":  (ex + 6.0, 39.0, 0),                   # LP5907 LDO (left column bottom)
        "SW1": (ex + 20.0, 31.0, 0),                  # BOOT (mid-strip, stacked above RESET)
        "SW2": (ex + 20.0, 37.0, 0),                  # RESET (stacked vertically so the pads don't mask-bridge)
        "D2":  (ex + 18.0, 14.0, 90), "C9": (ex + 22.0, 14.0, 0),  # VBUS ORing (vert SMA) + bulk
        "R8":  (ex + 18.0, 18.0, 0), "R9": (ex + 21.0, 18.0, 0),   # CC pulldowns
        "R10": (ex + 18.0, 26.0, 0), "C40": (ex + 21.0, 26.0, 0),  # §6.13 THRESH RC
        "J5":  (ex + 6.0, 3.5, 180),                  # USB-C on the TOP edge (rot180: mouth overhangs -y, pads on-board)
        "J1":  (ex + 29.0, 22.0, 90),                 # RJ-45 (Kinghelm FTP): mouth OVERHANGS the right edge; pads/posts/shield tabs on-board, mouth +X
    })
    # M3 mounts: one on the left edge in the clear band between the J_IN and J_OUT
    # courtyards; two in the right corners (freed by moving USB-C off the right edge),
    # flanking the overhanging RJ-45. For wider boards (N>=3) the overhang fills the
    # top/bottom edges across a long cable region, so add a mid-height mount in each
    # inter-cable gap (the clear band between one cable's sense parts and the next
    # cable's INA238) to keep the long board from flexing.
    mounts = [(4.0, BAND_Y), (W - 4.5, 5.0), (W - 4.5, H - 5.0)]
    if n >= 3:
        for i in range(n - 1):
            mounts.append((CX0 + i * PITCH + 20.15, BAND_Y))
    # CEC logo on the back, under the C6 (SMD, no THT) where B.Cu is clear — the
    # cable region's back is full of the J_IN/J_OUT through-hole pads.
    logo = (ex + 8.0, H / 2.0)
    return W, H, P, mounts, logo

def placement_hpwr():
    """Inline 12VHPWR Standard with the six 12V lanes FANNED OUT. J3 (PSU IN) and
    J4 (captive pigtail OUT) are 12V-2x6 connectors with a fixed 3 mm pin pitch;
    they are centered on the power section and the six +12V lanes splay symmetrically
    from that 3 mm pitch to a ~6 mm SENSE pitch, so each lane gets its OWN column
    with room for its in-line shunt -> RC input filter -> INA240 stacked straight
    down (short Kelvin, no staggering). Symmetric fan => equal-length lane pairs.
    The plug connectors overhang their edges (J3 top; J1/J5 right; J4 bottom). J4
    (OUT) is rot 180 so its mouth overhangs the bottom edge (correct OUT orientation,
    mirrors J3); the +12V load nets are remapped (gen-modules.py: J4 pin 6-j,
    interchangeable) so the lanes stay non-crossing despite the 180. Now that J3/J4
    sit centered (not in the corners), there is room for corner M3 mounts. The per-lane sense passives
    (RFH/RFL/CF + the INA bypass C10-C15) are placed here; the control-side
    decoupling (C1-C8, R1/R2/R7, D1) still comes via Update-from-Schematic."""
    PIT = 6.0
    LX = [4.0 + i * PIT for i in range(6)]            # fanned lanes: 4,10,16,22,28,34
    W, H = 58.0, 80.0
    cx = (LX[0] + LX[-1]) / 2.0                        # 19.0  power-section center
    jorg = cx - 7.5                                    # 11.5  J3/J4 pin-1 x (3 mm pitch)
    P = {"J3": (jorg, 6.5, 0)}                         # 12V-2x6 IN; shroud overhangs top
    # per-lane sense stack (top -> bottom): in-line 1 mΩ shunt -> RC input filter
    # (matched 10 Ω series Rf each leg + 470 nF Cdiff) -> INA240 (inputs facing UP
    # toward the shunt) -> INA V+ bypass below. All in the lane's own column.
    for i, x in enumerate(LX):
        P[f"RS{i+1}"]  = (x, 22.0, 90)               # 1 mΩ shunt, in-line (vertical)
        P[f"RFH{i+1}"] = (x - 1.6, 30.0, 90)         # series Rf, IN+ leg
        P[f"RFL{i+1}"] = (x + 1.6, 30.0, 90)         # series Rf, IN- leg
        P[f"CF{i+1}"]  = (x, 33.6, 90)               # differential cap, at the INA in
        P[f"U1{i}"]    = (x, 39.0, 90)               # INA240 (rot90 = 4.4mm wide, fits 6mm)
        P[f"C1{i}"]    = (x, 44.5, 0)                # INA V+ 100nF bypass (C10..C15)
    # J4 = pigtail OUT, rot 180 so its mouth faces OUT the bottom edge (mirrors J3
    # at the top) — the correct OUT orientation. Origin shifts +15mm in x so the
    # 180-reversed +12V pins land back in the same x-band; y set for a ~3mm bottom
    # overhang symmetric to J3. The +12V load nets are remapped (gen-modules.py) so
    # the lanes stay non-crossing into the reversed pins.
    P["J4"] = (jorg + 15.0, 73.5, 180)
    # --- control / power core + flash front end (right of the fanned lanes) ---
    P["U2"] = (44.0, 7.0, 0)                          # TJA1051T/3 CAN (top)
    P["D2"] = (43.0, 14.0, 90); P["C9"] = (47.0, 14.0, 0)   # VBUS ORing (vert) + bulk
    P["U1"] = (48.0, 30.0, 0)                         # ESP32-S3-MINI-1 (~16x21 crtyd)
    P["U3"] = (42.0, 45.0, 0)                         # LP5907 LDO
    P["R8"] = (41.0, 50.0, 0); P["R9"] = (45.0, 50.0, 0)    # CC pulldowns
    P["R5"] = (40.0, 56.0, 0); P["R6"] = (44.0, 56.0, 0)    # rail divider
    P["SW1"] = (52.0, 46.0, 0); P["SW2"] = (52.0, 52.0, 0)  # BOOT / RESET
    # 4 sideband taps, in the gap between J3's sideband pins (left) and the ESP
    P["R10"] = (38.0, 13.0, 0); P["R11"] = (38.0, 16.0, 0)
    P["R12"] = (38.0, 19.0, 0); P["R13"] = (38.0, 22.0, 0)
    P["J5"] = (54.0, 14.0, 90)                        # USB-C, right edge upper, opening +X
    # RJ-45 (J1): the shield posts SH1/SH2 stick out past the signal pins, so park
    # it low-right clear of the R-column/switches and the corner mount; mouth +X.
    P["J1"] = (42.0, 72.0, 90)                        # RJ-45, right edge lower, opening +X
    # Three M3 corner mounts: TL, TR, BL. The RJ-45's big jack body (~16.6x18.7mm
    # courtyard) fills the bottom-right corner, so a 4th mount can't go there; the
    # three big through-hole connectors (J3, J4, J1) anchor that side mechanically.
    mounts = [(4.0, 4.0), (W - 4.0, 4.0), (4.0, H - 4.0)]
    logo = (19.0, 53.0)                               # back copper, pad-free fan-in band
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
    comps, vals, nets = {}, {}, {}
    for m in re.finditer(r"\(comp\b", s):
        b = carve(s, m.start())
        r = re.search(r'\(ref "([^"]+)"', b); fp = re.search(r'\(footprint "([^"]*)"', b)
        vv = re.search(r'\(value "([^"]*)"', b)
        if r:
            comps[r.group(1)] = fp.group(1) if fp else ""
            vals[r.group(1)] = vv.group(1) if vv else ""
    for m in re.finditer(r"\(net\b", s):
        b = carve(s, m.start())
        nm = re.search(r'\(name "([^"]*)"\)', b)
        if not nm: continue
        nodes = [(rr.group(1), pp.group(1)) for nb in (carve(b, mm.start()) for mm in re.finditer(r"\(node\b", b))
                 for rr, pp in [(re.search(r'\(ref "([^"]+)"\)', nb), re.search(r'\(pin "([^"]+)"\)', nb))] if rr and pp]
        nets[nm.group(1)] = nodes
    return comps, vals, nets

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

def place(libid, ref, x, y, rot, padnet, code_of, *, gnd_all=False, flip=False, val=None):
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
    # Value property: set to the real component value and move it onto F.SilkS so
    # the value is visible on the board. Footprints default the Value to the
    # footprint name on the non-plotted F.Fab layer (so values never showed up);
    # the Reference stays on F.SilkS. Mechanical parts (mounts, logo) pass val=None
    # and keep their Fab default.
    if val:
        mv = re.search(r'\(property "Value" ', s)
        if mv:
            blk = carve(s, mv.start())
            nb = re.sub(r'^\(property "Value" "[^"]*"',
                        lambda m: f'(property "Value" "{val}"', blk, count=1)
            nb = nb.replace('(layer "F.Fab")', '(layer "F.SilkS")', 1)
            s = s[:mv.start()] + nb + s[mv.start() + len(blk):]
    out, pos = "", 0
    for m in re.finditer(r'\(pad "([^"]*)"', s):
        if m.start() < pos: continue
        blk = carve(s, m.start()); end = m.start() + len(blk); out += s[pos:m.start()]
        if rot:    # bake the footprint rotation into each pad angle (KiCad
                   # convention) so headless DRC doesn't report false within-
                   # footprint pad shorts on rotated parts
            blk = re.sub(r'\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?\)',
                         lambda mm: f"(at {mm.group(1)} {mm.group(2)} {(float(mm.group(3) or 0) + rot) % 360:g})",
                         blk, count=1)
        num = m.group(1); tag = None
        if gnd_all and num:
            tag = (code_of["GND"], "GND")
        elif num and (ref, num) in padnet:
            tag = padnet[(ref, num)]
        if tag:
            blk = blk[:-1].rstrip() + f'\n\t\t(net {tag[0]} "{tag[1]}")\n\t)'
        out += blk; pos = end
    return "\t" + (out + s[pos:]).strip() + "\n"

def gnd_planes(code, W, H):
    """Dual whole-board GND pour on BOTH inner layers (In1+In2), one zone spanning
    the two. EPS/PCIe run two GND inners (§6.7 high-current return + a quiet
    reference under the INA Kelvin sense); 12V lives on the OUTERS, split at the
    shunt, so an inner 12V plane would short the shunt. Emitted UNFILLED (kicad-cli
    cannot fill) — refill in the GUI with `B`."""
    ins = 0.25
    pts = f"(xy {ins} {ins}) (xy {ff(W-ins)} {ins}) (xy {ff(W-ins)} {ff(H-ins)}) (xy {ins} {ff(H-ins)})"
    return ('\t(zone\n\t\t(net %d)\n\t\t(net_name "GND")\n'
            '\t\t(layers "In1.Cu" "In2.Cu")\n\t\t(uuid "%s")\n\t\t(name "GND Plane")\n'
            '\t\t(hatch edge 0.5)\n\t\t(connect_pads yes\n\t\t\t(clearance 0.3)\n\t\t)\n'
            '\t\t(min_thickness 0.25)\n'
            '\t\t(fill yes\n\t\t\t(thermal_gap 0.3)\n\t\t\t(thermal_bridge_width 0.5)\n'
            '\t\t\t(island_removal_mode 0)\n\t\t)\n'
            '\t\t(polygon\n\t\t\t(pts\n\t\t\t\t%s\n\t\t\t)\n\t\t)\n\t)') % (code, U(), pts)

def build(dir_, base, n, kind):
    out = f"{ROOT}/modules/{dir_}/{base}.kicad_pcb"
    # Safety guard (FIRST, before reading the netlist): never silently clobber a
    # board that has been routed in the GUI (the ONE-SHOT bootstrap rule). If the
    # existing .kicad_pcb carries any track or via, refuse to overwrite unless
    # --force is passed. Protects the routed 12vhpwr-standard from a no-arg run.
    if os.path.exists(out) and "--force" not in sys.argv:
        if re.search(r"\n\s*\((?:segment|via)\b", open(out).read()):
            print(f"  SKIP {os.path.relpath(out, ROOT)}: already routed (tracks/vias present); "
                  f"pass --force to overwrite", file=sys.stderr)
            return
    netf = f"{ROOT}/modules/{dir_}/{base}.net"
    if not os.path.exists(netf):
        print(f"  SKIP {base}: no exported netlist ({base}.net) — run "
              f"`kicad-cli sch export netlist` first", file=sys.stderr)
        return
    comps, vals, nets = parse_netlist(netf)
    names = [x for x in sorted(nets) if x]
    code_of = {x: i + 1 for i, x in enumerate(names)}
    padnet = {(r, p): (code_of[x], x) for x, nodes in nets.items() if x for (r, p) in nodes}
    W, H, P, mounts, logo = placement_hpwr() if kind == "hpwr" else placement(n)

    fps = []
    for ref, (x, y, rot) in P.items():
        lib = comps.get(ref)
        if lib: fps.append(place(lib, ref, x, y, rot, padnet, code_of, val=vals.get(ref)))
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
    zones = (gnd_planes(code_of["GND"], W, H) + "\n") if (kind == "cable" and "GND" in code_of) else ""
    doc = ("(kicad_pcb\n\t(version 20260206)\n\t(generator \"cec-gen-module-pcb\")\n"
           "\t(generator_version \"10.0\")\n"
           "\t(general\n\t\t(thickness 1.6)\n\t\t(legacy_teardrops no)\n\t)\n"
           "\t(paper \"A4\")\n" + LAYERS + "\n\t(setup\n" + stackup() +
           "\n\t\t(pad_to_mask_clearance 0)\n"
           "\t\t(allow_soldermask_bridges_in_footprints no)\n\t)\n"
           + netdecl + "\n" + "\n".join(fps) + "\n" + "\n".join(e) + "\n"
           + zones + note + "\n\t(embedded_fonts no)\n)\n")
    open(out, "w").write(doc)
    print(f"{os.path.relpath(out, ROOT)}  N={n} footprints={len(fps)} board={W:.0f}x{H:.0f}mm")

# Optional CLI filter: `gen-module-pcb.py eps-8pin` builds only that board. With
# no board args it builds all (the original behavior); a routed board is then
# SKIPPED unless --force (see build()). Flags (--force) are not board names.
targets = {a for a in sys.argv[1:] if not a.startswith("-")}
for d, b, n, kind in BOARDS:
    if targets and not (d in targets or b in targets):
        continue
    build(d, b, n, kind)
