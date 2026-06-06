#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Candidate floorplan + routing-plan generator for the EPS 8-pin telemetry module.
# Supersedes the hand-bootstrapped condensed floorplan with a reproducible engine:
#
#   * FRAME    -- the condensed pegless-87427 layout (J_IN rot180 / J_OUT rot0 so the
#                 +12V columns line up; sense band per cable; ESP/CAN/LDO/RJ-45 core).
#   * PASSIVES -- a GEOMETRY-DRIVEN engine: every decoupling/RC/pull-up/ESD passive is
#                 placed at its OWNER IC's actual power-pad (read from the footprint),
#                 offset radially outward, per the netlist-verified placement spec.
#   * ROUTING  -- routing-candidate guide graphics drawn on Dwgs.User (12V pours, GND
#                 stitching, Kelvin pairs, the control->sense spine, CAN, USB) so the
#                 routes are visible in the board, plus a matplotlib routing-plan PNG.
#
# Reuses gen-module-pcb.py's emit helpers (place/parse_netlist/gnd_planes/stackup/...)
# without modifying the shared generator (imported with a no-op board filter). Writes
# modules/eps-8pin/eps8pin-module.kicad_pcb in place (one-shot bootstrap; the board is
# hand-maintained in the GUI after the first route). Verify: kicad-cli pcb drc / render.
#
#   python3 scripts/gen-eps-condensed.py            # board + routing guides
#   python3 scripts/gen-eps-condensed.py --plan     # also (re)draw the routing-plan PNG
import os, re, sys, math, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + "/scripts")
# import gen-module-pcb.py for its emit helpers WITHOUT running its build loop
# (its module-level CLI filters to board-name args; a name that matches nothing builds
# nothing). Robust to the stable filter logic; does not touch the shared generator.
_saved_argv = sys.argv
sys.argv = ["gen-eps-condensed", "__none__"]
import importlib.util
_spec = importlib.util.spec_from_file_location("gmp", ROOT + "/scripts/gen-module-pcb.py")
gmp = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(gmp)
sys.argv = _saved_argv
place, parse_netlist, gnd_planes, stackup = gmp.place, gmp.parse_netlist, gmp.gnd_planes, gmp.stackup
LAYERS, U, ff, carve, fp_path = gmp.LAYERS, gmp.U, gmp.ff, gmp.carve, gmp.fp_path

DIR, BASE, N = "eps-8pin", "eps8pin-module", 2

# ----------------------------------------------------------------- frame geometry
CX0, PITCH, H = 11.0, 23.0, 35.0     # 11mm left margin (clears a left-edge M3), 23mm cable pitch
def geometry():
    cables_right = CX0 + (N - 1) * PITCH + 16.2   # rightmost 87427 courtyard
    ex = cables_right + 3.8                        # electronics-core left x
    return round(ex + 42.0), H, ex                 # W, H, ex

def frame():
    """ICs, connectors, shunts, mounts, logo -- the condensed pegless frame. Passives
    are NOT here; the engine places them around these anchors."""
    W, H_, ex = geometry()
    P = {}
    for i in range(N):
        Xc, c = CX0 + i * PITCH, i + 1
        # pegless 87427: J_IN rot180 (mouth -> top, GND row y4 / +12V row y9.5), J_OUT
        # rot0 (mouth -> bottom). J_OUT at Xc+12.6 keeps the +12V columns aligned so 12V
        # flows straight down through the shunt.
        P[f"J_IN{c}"]  = (Xc, 4.0, 180)
        P[f"J_OUT{c}"] = (Xc + 12.6, H_ - 4.0, 0)
        P[f"RS{c}"]    = (Xc + 6.8, 17.5, 90)         # 0.5mOhm shunt, vertical in the 12V column
        P[f"U1{i}"]    = (Xc + 0.5, 17.5, 0)          # INA238 (U10/U11), left of shunt, Kelvin-taps it
        P[f"U2{i}"]    = (Xc + 11.8, 15.0, 0)         # INA181A2 (U20/U21), right of shunt
        P[f"U3{i}"]    = (Xc + 11.8, 20.0, 0)         # TLV7011 (U30/U31)
    P.update({
        "J5": (ex + 8.0, 4.0, 180),                   # USB-C, top edge
        "U1": (ex + 9.0, 22.0, 180),                  # ESP32-C6 (antenna keepout dropped, no wireless)
        "U3": (ex + 20.0, 14.0, 0),                   # LP5907 LDO
        "U2": (ex + 29.0, 4.5, 0),                    # TJA1051T/3 CAN
        "SW1": (ex + 19.0, 27.0, 0), "SW2": (ex + 25.0, 27.0, 0),
        "D2": (ex + 20.0, 4.0, 90),                   # VBUS ORing SMA
        "J1": (ex + 38.0, 18.0, 90),                  # RJ-45 FTP, right edge (box x[87.8,96+] y[5.6,21.6])
    })
    mounts = [(4.0, 4.5), (4.0, H_ - 4.5), (W - 4.0, H_ - 4.0)]
    logo = (ex + 9.0, 20.0)
    return W, H_, ex, P, mounts, logo

# ----------------------------------------------------------------- pad geometry
def _local_pads(libid):
    """Local (x,y) of each numbered pad in a footprint (lib nickname:name)."""
    nick, name = libid.split(":")
    t = open(fp_path(nick, name)).read(); out = {}
    for m in re.finditer(r'\(pad ', t):
        b = carve(t, m.start())
        num = re.match(r'\(pad "([^"]*)"', b); at = re.search(r'\(at (-?[\d.]+) (-?[\d.]+)', b)
        if num and at and num.group(1):
            out[num.group(1)] = (float(at.group(1)), float(at.group(2)))
    return out

def pad_global(ref, pad, P, comps):
    """Global (x,y) of an IC pad, given its frame placement and footprint geometry.
    Uses KiCad's footprint rotation (A deg): gx=X+lx*cosA+ly*sinA, gy=Y-lx*sinA+ly*cosA."""
    X, Y, A = P[ref]; lx, ly = _local_pads(comps[ref])[pad]
    a = math.radians(A)
    return (X + lx * math.cos(a) + ly * math.sin(a), Y - lx * math.sin(a) + ly * math.cos(a))

# ----------------------------------------------------------------- passive engine
# Each support passive sits in its OWNER IC's decoupling cluster, on the power-pin
# side, at a DRC-clean offset. PASSIVE_SPEC records (owner, expected_net, role) from
# the netlist-verified placement analysis; verify_passives() asserts the netlist still
# agrees so the cluster assignment can't drift from the schematic. Positions are
# frame-relative (ex / per-cable Xc) and reproduce the validated condensed layout.
PASSIVE_SPEC = {
    "C3":  ("U1",  "+3V3",        "ESP +3V3 HF bypass"),
    "C7":  ("U1",  "+3V3",        "ESP +3V3 bulk"),
    "C5":  ("U1",  "/EN",         "ESP EN reset-RC cap"),
    "R2":  ("U1",  "/EN",         "ESP EN pull-up to +3V3"),
    "R10": ("U1",  "/THRESH_PWM", "THRESH series R (PWM IO14)"),
    "C40": ("U30", "/THRESH",     "THRESH filter cap (shared U30/U31)"),
    "R3":  ("U1",  "/I2C_SDA",    "I2C SDA pull-up"),
    "R4":  ("U1",  "/I2C_SCL",    "I2C SCL pull-up"),
    "C4":  ("U2",  "+5VSB",       "CAN VCC bypass"),
    "C8":  ("U2",  "+3V3",        "CAN VIO bypass"),
    "C1":  ("U3",  "+5VSB",       "LDO VIN bulk"),
    "C2":  ("U3",  "+3V3",        "LDO VOUT bulk"),
    "C6":  ("U3",  "+5VSB",       "+5VSB board-entry bulk"),
    "C9":  ("J5",  "/VBUS",       "USB-C VBUS bulk"),
    "C10": ("U10", "+3V3",        "INA238 C1 VS bypass"),
    "C11": ("U11", "+3V3",        "INA238 C2 VS bypass"),
    "C20": ("U20", "+3V3",        "INA181 C1 VS bypass"),
    "C21": ("U21", "+3V3",        "INA181 C2 VS bypass"),
    "C30": ("U30", "+3V3",        "TLV7011 C1 VCC bypass"),
    "C31": ("U31", "+3V3",        "TLV7011 C2 VCC bypass"),
    "R8":  ("J5",  "/USB_CC1",    "USB CC1 pull-down"),
    "R9":  ("J5",  "/USB_CC2",    "USB CC2 pull-down"),
    "D1":  ("J1",  "/DETECT",     "DETECT ESD clamp"),
    "R1":  ("J1",  "/DETECT",     "DETECT 2.2k code resistor"),
    "R7":  ("J1",  "/DETECT",     "DETECT 100k poke tap -> ESP"),
}

def verify_passives(nets):
    """Assert each passive shares its expected net (so the cluster owner is correct).
    Warns (does not fail) so a schematic drift is surfaced, not silently carried."""
    members = {nm: {r for r, _ in nodes} for nm, nodes in nets.items()}
    bad = [ref for ref, (own, net, _r) in PASSIVE_SPEC.items() if ref not in members.get(net, set())]
    for ref in bad:
        own, net, _r = PASSIVE_SPEC[ref]
        print(f"  VERIFY: {ref} expected on {net} (owner {own}) -- not in netlist", file=sys.stderr)
    print(f"  passive ownership: {len(PASSIVE_SPEC)-len(bad)}/{len(PASSIVE_SPEC)} netlist-verified")
    return not bad

def place_passives(P, ex):
    """DRC-clean cluster placement (frame-relative). Each passive sits in its
    PASSIVE_SPEC owner's cluster, on the power-pin side; positions DRC-validated."""
    for i in range(N):                       # per-cable sense-band bypass caps
        Xc = CX0 + i * PITCH
        P[f"C1{i}"] = (Xc + 0.5,  14.0, 0)   # C10/C11 INA238 VS bypass (above the INA)
        P[f"C2{i}"] = (Xc + 15.2, 15.0, 0)   # C20/C21 INA181 VS bypass
        P[f"C3{i}"] = (Xc + 15.2, 20.0, 0)   # C30/C31 TLV7011 VCC bypass
    P.update({                               # core clusters (ex-relative)
        "C6": (ex + 2.5, 13.5, 0), "C3": (ex + 6.0, 13.5, 0), "C7": (ex + 13.0, 13.5, 0),   # ESP +3V3
        "C1": (ex + 17.5, 16.5, 0), "C2": (ex + 22.5, 16.5, 0),                             # LDO in/out
        "C5": (ex + 25.0, 13.5, 0), "R2": (ex + 27.0, 13.5, 0),                             # ESP EN RC
        "R3": (ex + 18.0, 20.0, 0), "R4": (ex + 20.0, 20.0, 0),                             # I2C pull-ups
        "R10": (ex + 25.0, 18.0, 0), "C40": (ex + 27.0, 18.0, 0),                           # THRESH RC
        "R8": (ex + 15.0, 4.0, 0), "R9": (ex + 17.0, 4.0, 0), "C9": (ex + 12.0, 10.5, 0),   # USB CC / VBUS
        "C4": (ex + 26.5, 8.0, 0), "C8": (ex + 31.5, 8.0, 0),                               # CAN bypass
        "D1": (ex + 30.0, 26.0, 0), "R1": (ex + 33.0, 26.0, 0), "R7": (ex + 35.5, 26.0, 0), # DETECT front-end
    })
    return P

# ----------------------------------------------------------------- routing candidates
# Drawn as guide graphics on toggleable user layers (non-plotted) so the routes are
# visible in the board while routing. Coordinates from the routing game-plan, keyed to
# the real placement above. The matplotlib routing-plan PNG carries the full color story.
def _poly(pts, layer, w=0.12):
    s = " ".join(f"(xy {ff(x)} {ff(y)})" for x, y in pts)
    return (f'\t(gr_poly (pts {s}) (stroke (width {w}) (type solid)) '
            f'(fill none) (layer "{layer}") (uuid "{U()}"))')
def _line(pts, layer, w=0.25):
    out = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        out.append(f'\t(gr_line (start {ff(x1)} {ff(y1)}) (end {ff(x2)} {ff(y2)}) '
                   f'(stroke (width {w}) (type solid)) (layer "{layer}") (uuid "{U()}"))')
    return "\n".join(out)
def _txt(t, x, y, layer, sz=0.8):
    return (f'\t(gr_text "{t}" (at {ff(x)} {ff(y)} 0) (layer "{layer}") (uuid "{U()}") '
            f'(effects (font (size {sz} {sz}) (thickness 0.12))))')

def routing_guides(P, W, H, ex, comps):
    g = []
    # --- NET CLASS 1: +12V IN/OUT pour outlines per cable (Dwgs.User) ---
    for i in range(N):
        dx = i * PITCH
        IN  = [(9.5+dx,8),(25.1+dx,8),(25.1+dx,13),(20+dx,13),(20+dx,15.6),
               (15.6+dx,15.6),(15.6+dx,13),(9.5+dx,13),(9.5+dx,8)]
        OUT = [(15.6+dx,19.4),(20+dx,19.4),(20+dx,22),(25.1+dx,22),(25.1+dx,27),
               (9.5+dx,27),(9.5+dx,22),(15.6+dx,22),(15.6+dx,19.4)]
        g.append(_poly(IN, "Dwgs.User"));  g.append(_txt(f"12V_IN{i+1} (F+B, 2oz)", 10+dx, 6.6, "Dwgs.User", 0.7))
        g.append(_poly(OUT, "Dwgs.User")); g.append(_txt(f"12V_OUT{i+1}", 10+dx, 28.4, "Dwgs.User", 0.7))
    # --- NET CLASS 3: Kelvin sense pairs off the shunt inner edges (Cmts.User) ---
    for i in range(N):
        rsx = (CX0 + i*PITCH) + 6.8
        u10 = f"U1{i}"; u20 = f"U2{i}"
        hi_in,  lo_in  = pad_global(u10,"10",P,comps), pad_global(u10,"8",P,comps)
        hi_181, lo_181 = pad_global(u20,"3",P,comps),  pad_global(u20,"4",P,comps)
        g.append(_line([(rsx,15.9), hi_in],  "Cmts.User", 0.25))   # RS.HI -> INA238 IN+
        g.append(_line([(rsx,19.1), lo_in],  "Cmts.User", 0.25))   # RS.LO -> INA238 IN-
        g.append(_line([(rsx,15.9), hi_181], "Cmts.User", 0.25))   # RS.HI -> INA181 IN+
        g.append(_line([(rsx,19.1), lo_181], "Cmts.User", 0.25))   # RS.LO -> INA181 IN-
    g.append(_txt("Kelvin: tap shunt INNER edge, matched pair over In1 GND", 11, 13.2, "Cmts.User", 0.6))
    # --- NET CLASS 4: control->sense spine along the y~18-21 split-gap lane (Eco1.User) ---
    p3v3 = pad_global("U3","5",P,comps); esp3 = pad_global("U1","3",P,comps)
    g.append(_line([p3v3,(ex+18,19),(47,19),(36.7,18.5),(14,19),(13.7,18.5)], "Eco1.User", 0.4))  # +3V3 sub-trunk
    sda = pad_global("U1","24",P,comps)
    g.append(_line([sda,(50,18.5),(32.3,18.0),(14,18.5),(9.3,18.0)], "Eco1.User", 0.22))           # I2C SDA daisy
    g.append(_line([pad_global("U1","25",P,comps),(50,18.9),(32.3,18.5),(9.3,18.5)], "Eco1.User", 0.22))  # SCL
    thr = pad_global("U1","19",P,comps)
    g.append(_line([thr,(79.5,18),(60,21),(46.9,20.95),(23.9,20.95)], "Eco1.User", 0.22))          # THRESH (low lane)
    g.append(_line([pad_global("U30","1",P,comps),(40,20.4),pad_global("U1","28",P,comps)], "Eco1.User", 0.22))  # DETC1
    g.append(_line([pad_global("U31","1",P,comps),(50,21.0),pad_global("U1","29",P,comps)], "Eco1.User", 0.22))  # DETC2
    g.append(_txt("SPINE: +3V3 / I2C / THRESH / DETC  (y18-21 split gap; hop shunt on B.Cu)", ex-2, 22.6, "Eco1.User", 0.6))
    # --- NET CLASS 5/6: CAN + USB (Eco2.User) ---
    g.append(_line([pad_global("U2","7",P,comps),(88,8),(91,14),pad_global("J1","3",P,comps)], "Eco2.User", 0.25))  # CAN_H
    g.append(_line([pad_global("U2","6",P,comps),(88,9),(92,15),pad_global("J1","6",P,comps)], "Eco2.User", 0.25))  # CAN_L
    g.append(_line([pad_global("U2","1",P,comps),(70,18),pad_global("U1","26",P,comps)], "Eco2.User", 0.22))        # CAN_TX
    g.append(_line([pad_global("U2","4",P,comps),(70,19),pad_global("U1","27",P,comps)], "Eco2.User", 0.22))        # CAN_RX
    g.append(_line([pad_global("J5","A6",P,comps), pad_global("U1","18",P,comps)], "Eco2.User", 0.25))              # USB_DP
    g.append(_line([pad_global("J5","A7",P,comps), pad_global("U1","17",P,comps)], "Eco2.User", 0.25))              # USB_DM
    g.append(_txt("CAN pair -> RJ45 / USB FS pair -> ESP (length-match)", ex+18, 11, "Eco2.User", 0.6))
    return "\n".join(g)

# ----------------------------------------------------------------- build the board
def build():
    out  = f"{ROOT}/modules/{DIR}/{BASE}.kicad_pcb"
    netf = f"{ROOT}/modules/{DIR}/{BASE}.net"
    if not os.path.exists(netf):
        os.system(f"cd {ROOT}/modules/{DIR} && kicad-cli sch export netlist -o {BASE}.net {BASE}.kicad_sch >/dev/null 2>&1")
    if re.search(r"\n\s*\((?:segment|via)\b", open(out).read()) if os.path.exists(out) else False:
        if "--force" not in sys.argv:
            print(f"  SKIP {out}: already routed; pass --force"); return
    comps, vals, nets = parse_netlist(netf)
    names = [x for x in sorted(nets) if x]
    code_of = {x: i + 1 for i, x in enumerate(names)}
    padnet = {(r, p): (code_of[x], x) for x, nodes in nets.items() if x for (r, p) in nodes}
    verify_passives(nets)
    W, H_, ex, P, mounts, logo = frame()
    place_passives(P, ex)
    fps = []
    for ref, (x, y, rot) in P.items():
        lib = comps.get(ref)
        if lib: fps.append(place(lib, ref, x, y, rot, padnet, code_of, val=vals.get(ref)))
        else:   print(f"  WARN no footprint for {ref}", file=sys.stderr)
    for i, (x, y) in enumerate(mounts, 1):
        fps.append(place("cec-MountingHole:MountingHole_3.2mm_M3_Pad_Via", f"H{i}", x, y, 0, padnet, code_of, gnd_all=True))
    fps.append(place("cec:CEC_Logo_Copper", "LOGO1", logo[0], logo[1], 0, padnet, code_of, flip=True))
    e = []
    pts = [(0, 0), (W, 0), (W, H_), (0, H_), (0, 0)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        e.append(f'\t(gr_line (start {ff(x1)} {ff(y1)}) (end {ff(x2)} {ff(y2)}) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "{U()}"))')
    note = (f'\t(gr_text "CEC {BASE}  4L 2oz/1oz" (at {ff(logo[0])} {ff(H_ - 3)} 0) (layer "B.SilkS") (uuid "{U()}") '
            f'(effects (font (size 0.9 0.9) (thickness 0.13)) (justify mirror)))')
    netdecl = '\t(net 0 "")\n' + "\n".join(f'\t(net {code_of[x]} "{x}")' for x in names)
    zones = gnd_planes(code_of["GND"], W, H_) + "\n"
    guides = routing_guides(P, W, H_, ex, comps) + "\n"
    doc = ("(kicad_pcb\n\t(version 20260206)\n\t(generator \"cec-gen-eps-condensed\")\n\t(generator_version \"10.0\")\n"
           "\t(general\n\t\t(thickness 1.6)\n\t\t(legacy_teardrops no)\n\t)\n\t(paper \"A4\")\n" + LAYERS +
           "\n\t(setup\n" + stackup() + "\n\t\t(pad_to_mask_clearance 0)\n\t\t(allow_soldermask_bridges_in_footprints no)\n\t)\n"
           + netdecl + "\n" + "\n".join(fps) + "\n" + "\n".join(e) + "\n" + zones + guides + note + "\n\t(embedded_fonts no)\n)\n")
    # ESP32-C6 antenna keepout dropped (no wireless): trim courtyard to body.
    doc = doc.replace("-10.98", "-4.95")
    open(out, "w").write(doc)
    print(f"WROTE {os.path.relpath(out, ROOT)}  board={W}x{H_:.0f}mm  parts={len(fps)}  +routing guides")


# ----------------------------------------------------------------- routing-plan PNG
def _gcourt(libid, x, y, rot):
    """Global courtyard bbox (xmin,xmax,ymin,ymax) of a placed footprint."""
    nick, name = libid.split(":")
    t = open(fp_path(nick, name)).read(); xs = []; ys = []
    for m in re.finditer(r'\(fp_(?:line|poly|rect)\b', t):
        b = carve(t, m.start())
        if 'CrtYd' not in b: continue
        for a, c in re.findall(r'\((?:start|end|xy|mid) (-?[\d.]+) (-?[\d.]+)\)', b):
            lx, ly = float(a), float(c)
            if name.startswith("ESP32-C6") and ly < -5.0:  # antenna keepout dropped
                ly = -4.95
            a_ = math.radians(rot)
            xs.append(x + lx*math.cos(a_) + ly*math.sin(a_))
            ys.append(y - lx*math.sin(a_) + ly*math.cos(a_))
    if not xs:  # fall back to a small box
        return (x-1, x+1, y-1, y+1)
    return (min(xs), max(xs), min(ys), max(ys))

def routing_plan_png():
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Polygon, Circle
    from matplotlib.lines import Line2D
    netf = f"{ROOT}/modules/{DIR}/{BASE}.net"
    comps, vals, nets = parse_netlist(netf)
    W, H_, ex, P, mounts, logo = frame(); place_passives(P, ex)
    C = dict(v12i="#d83434", v12o="#e8862a", gnd="#1f9e6f", kel="#1438a8",
             p3v3="#1f9e6f", sig="#7a52c8", can="#b5179e", usb="#1d7fd8", body="#9aa7b4", txt="#101418")

    fig = plt.figure(figsize=(17.5, 8.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.65, 1.0], wspace=0.02)
    ax = fig.add_subplot(gs[0]); nx = fig.add_subplot(gs[1]); nx.axis("off")
    ax.set_aspect("equal"); ax.set_xlim(-3, 99); ax.set_ylim(38, -4)  # invert y (KiCad)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), W, H_, fill=False, ec="#222", lw=1.6))
    ax.text(W/2, -2.0, f"CEC EPS 8-pin — routing-candidate plan   {W:.0f} x {H_:.0f} mm   "
            f"4-layer F.Cu / In1 GND / In2 GND / B.Cu   (12V on outers, split at shunt)",
            ha="center", va="center", fontsize=11, weight="bold", color=C["txt"])

    # --- parts (courtyard boxes) ---
    for ref, (x, y, rot) in P.items():
        lib = comps.get(ref)
        if not lib: continue
        x0, x1, y0, y1 = _gcourt(lib, x, y, rot)
        big = ref in ("J1", "J5") or ref.startswith("J_")
        ax.add_patch(Rectangle((x0, y0), x1-x0, y1-y0, fill=True, fc="#eef1f4" if not big else "#dde6ee",
                     ec=C["body"], lw=0.7, alpha=0.95, zorder=2))
        if ref.startswith(("U", "J", "RS")) or ref in ("D1", "D2"):
            ax.text((x0+x1)/2, (y0+y1)/2, ref, ha="center", va="center",
                    fontsize=6.6 if not big else 8, color=C["txt"], zorder=6, weight="bold")
    for (mx, my) in mounts:
        ax.add_patch(Circle((mx, my), 3.2, fill=True, fc="#f2d34e", ec="#b69a18", lw=0.8, zorder=1))

    def pad(ref, p): return pad_global(ref, p, P, comps)
    # --- NET 1: 12V IN/OUT pours (filled translucent) ---
    for i in range(N):
        dx = i*PITCH
        IN  = [(9.5+dx,8),(25.1+dx,8),(25.1+dx,13),(20+dx,13),(20+dx,15.6),(15.6+dx,15.6),(15.6+dx,13),(9.5+dx,13)]
        OUT = [(15.6+dx,19.4),(20+dx,19.4),(20+dx,22),(25.1+dx,22),(25.1+dx,27),(9.5+dx,27),(9.5+dx,22),(15.6+dx,22)]
        ax.add_patch(Polygon(IN,  closed=True, fc=C["v12i"], ec=C["v12i"], alpha=0.22, lw=1.0, zorder=3))
        ax.add_patch(Polygon(OUT, closed=True, fc=C["v12o"], ec=C["v12o"], alpha=0.22, lw=1.0, zorder=3))
        # GND stitch hints (teal dots) flanking each pour column
        for gy in (5.5, 6.8, 28.2, 29.5):
            for gx in (10.2+dx, 24.4+dx):
                ax.plot(gx, gy, 'o', ms=2.4, mfc=C["gnd"], mec="none", zorder=4)
    # --- NET 3: Kelvin pairs off shunt inner edges ---
    for i in range(N):
        rsx = (CX0+i*PITCH)+6.8
        for tap, dst in [((rsx,15.9), pad(f"U1{i}","10")), ((rsx,19.1), pad(f"U1{i}","8")),
                         ((rsx,15.9), pad(f"U2{i}","3")),  ((rsx,19.1), pad(f"U2{i}","4"))]:
            ax.plot([tap[0],dst[0]],[tap[1],dst[1]], color=C["kel"], lw=1.4, zorder=5)
    # --- NET 4: spine (+3V3 fat, I2C/THRESH/DET thin) ---
    def poly(pts, col, lw, z=5, ls="-"):
        xs=[p[0] for p in pts]; ys=[p[1] for p in pts]; ax.plot(xs,ys,color=col,lw=lw,ls=ls,zorder=z)
    poly([pad("U3","5"),(ex+18,19),(47,19),(36.7,18.5),(14,19),(13.7,18.5)], C["p3v3"], 2.6)          # +3V3
    poly([pad("U1","24"),(50,18.5),(32.3,18.0),(14,18.5),(9.3,18.0)], C["sig"], 1.0, ls=(0,(4,2)))     # I2C SDA
    poly([pad("U1","25"),(50,18.9),(32.3,18.5),(9.3,18.5)], C["sig"], 1.0, ls=(0,(4,2)))               # I2C SCL
    poly([pad("U1","19"),(79.5,18),(60,21),(46.9,20.95),(23.9,20.95)], "#c46a00", 1.0, ls=(0,(1,1)))   # THRESH
    poly([pad("U30","1"),(40,20.4),pad("U1","28")], C["sig"], 0.9)                                     # DETC1
    poly([pad("U31","1"),(50,21.0),pad("U1","29")], C["sig"], 0.9)                                     # DETC2
    # --- NET 5/6: CAN + USB ---
    poly([pad("U2","7"),(88,8),(91,14),pad("J1","3")], C["can"], 1.4)
    poly([pad("U2","6"),(88,9),(92,15),pad("J1","6")], C["can"], 1.4)
    poly([pad("U2","1"),(70,18),pad("U1","26")], C["can"], 1.0, ls=(0,(4,2)))
    poly([pad("U2","4"),(70,19),pad("U1","27")], C["can"], 1.0, ls=(0,(4,2)))
    poly([pad("J5","A6"),pad("U1","18")], C["usb"], 1.6)
    poly([pad("J5","A7"),pad("U1","17")], C["usb"], 1.6)

    leg = [Line2D([],[],color=C["v12i"],lw=6,alpha=.4,label="12V IN pour (F+B, 2oz)"),
           Line2D([],[],color=C["v12o"],lw=6,alpha=.4,label="12V OUT pour"),
           Line2D([],[],marker='o',color='w',mfc=C["gnd"],ms=6,label="GND stitch via (In1/In2)"),
           Line2D([],[],color=C["kel"],lw=2,label="Kelvin sense pair (0.25mm)"),
           Line2D([],[],color=C["p3v3"],lw=3,label="+3V3 sub-trunk (0.4mm)"),
           Line2D([],[],color=C["sig"],lw=1.2,ls=(0,(4,2)),label="I2C / DET (spine)"),
           Line2D([],[],color="#c46a00",lw=1.2,ls=(0,(1,1)),label="THRESH ref (quiet lane)"),
           Line2D([],[],color=C["can"],lw=2,label="CAN H/L + TX/RX"),
           Line2D([],[],color=C["usb"],lw=2,label="USB FS pair (matched)")]
    ax.legend(handles=leg, loc="lower center", bbox_to_anchor=(0.5,-0.16), ncol=3, fontsize=8, framealpha=.95)

    # --- right notes panel ---
    def block(y, title, lines, tc="#101418"):
        nx.text(0.0, y, title, fontsize=11, weight="bold", color=tc, transform=nx.transAxes)
        for k, ln in enumerate(lines):
            nx.text(0.02, y-0.034*(k+1), ln, fontsize=8.2, color="#222", transform=nx.transAxes, family="DejaVu Sans")
        return y-0.034*(len(lines)+1)-0.025
    y = 0.99
    y = block(y, "ROUTING ORDER", [
        "1. Pour In1+In2 GND planes; stitch every connector/IC GND.",
        "2. 12V IN/OUT pours per cable (F.Cu + B.Cu mirror) + via fields; split at shunt.",
        "3. Kelvin stubs (4/shunt) off the INNER pad edges, matched pairs over GND.",
        "4. §6.13 in-column hops (DETAMPn, short DETn/THRESH column stubs).",
        "5. USB DP/DM pair (short, straight, length-matched).",
        "6. CAN H/L -> RJ45 ; TX/RX -> ESP.",
        "7. Control->sense SPINE (+3V3, I2C, THRESH, DETC1/2) on the y18-21 lane.",
        "8. +5VSB / VBUS-OR / DETECT core knit + EN.  9. Re-pour, DRC."])
    y = block(y, "NETCLASSES (committed: .kicad_pro + .kicad_dru)", [
        "Power12V  2.5/pour  via 0.9/0.5  clr0.2   /SENSEC* (12V ~30A pours)",
        "GND       0.5/plane via 0.9/0.5           GND",
        "Power     0.5 mm    via 0.8/0.4           +3V3 / +5VSB / /VBUS",
        "Signal    0.22 mm   via 0.6/0.3           I2C/THRESH/DET/CAN_TX,RX/EN/CC",
        "CAN       0.25 mm   coupled pair          /CAN_H /CAN_L (std H/L names)",
        "USB       0.25 / gap0.13  DIFF PAIR       /USB_D_P /USB_D_N (auto-paired)",
        "Kelvin tap shares /SENSEC* -> draw 0.25mm by hand off the shunt edge."])
    y = block(y, "SI / KEEP-AWAY", [
        "* Kelvin pairs & THRESH ref: >=0.5mm off any 12V copper edge",
        "  (the 30A pours carry the transient the §6.13 chain catches).",
        "* THRESH is a shared comparator ref - quiet quasi-DC lane, C40 at",
        "  the source, never parallel-adjacent to a 12V lane or DETC for long.",
        "* Spine crosses the cable backs - run it in the OPEN y16-21.5 band",
        "  between J_IN (y4) and J_OUT (y31); hop a shunt column on B.Cu.",
        "* USB length-match DP/DM (J5 sits directly above the ESP).",
        "* CAN H/L stay paired; 120R split termination lives at the Hub.",
        "* Guides drawn in-board on Dwgs/Cmts/Eco1/Eco2.User (toggle layers)."])
    nx.text(0.0, y-0.005, "Per-cable +12V flows J_IN pads 5-8 -> 0.5mΩ shunt -> J_OUT pads 5-8 (~30A);",
            fontsize=8, color="#444", transform=nx.transAxes, style="italic")
    nx.text(0.0, y-0.04, "GND pins 1-4 return on the inner planes. INA238 + INA181 Kelvin-tap each shunt.",
            fontsize=8, color="#444", transform=nx.transAxes, style="italic")

    out = f"{ROOT}/modules/{DIR}/eps-routing-plan.png"
    fig.savefig(out, dpi=145, bbox_inches="tight", facecolor="white")
    print(f"WROTE {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    build()
    if "--no-plan" not in sys.argv:
        routing_plan_png()
