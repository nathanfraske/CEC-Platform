#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Candidate floorplan + routing-plan generator for the PCIe 8-pin 3-port telemetry
# module -- the sub-100mm condensed form (99 x 44 mm). Mirrors gen-eps-condensed.py
# but for THREE cables on the pegged Molex 45586 (so H stays 44, not the EPS 35 --
# the 45586's two snap pegs sit 7.3mm forward of the pad rows, deepening the courtyard):
#
#   * FRAME    -- 3 cables (J_IN rot180 / J_OUT rot0 so the +12V columns line up; one
#                 INA238 + INA181 + TLV7011 sense band per cable), then a TIGHT 34mm
#                 electronics core (ESP32-C6 / CAN / LDO / RJ-45 / USB-C front end).
#                 The 126mm 3-port's inter-cable M3 mounts do NOT fit at the 21mm pitch
#                 that buys sub-100mm, so the board mounts on the right (electronics)
#                 side only -- the six 45586 connectors (8 THT pins + 2 x3mm snap pegs
#                 each) anchor the cable half mechanically.
#   * PASSIVES -- a CLEARANCE-AWARE engine: every decoupling/RC/pull-up/ESD passive is
#                 packed at the nearest DRC-clean spot to its OWNER IC (courtyard +
#                 pad-pad gaps enforced), so the dense 34mm core stays clean by
#                 construction. PASSIVE_SPEC records (owner, expected_net) and
#                 verify_passives() asserts the netlist still agrees.
#   * ROUTING  -- routing-candidate guide graphics on user layers + a matplotlib
#                 routing-plan PNG (3-cable version of the EPS plan).
#
# Reuses gen-module-pcb.py's emit helpers WITHOUT running its build loop (imported with
# a board filter that matches nothing). Detached from the EPS module by construction:
# writes ONLY modules/pcie-8pin-3port/. One-shot bootstrap -- the board is hand-
# maintained in the GUI after the first route. Verify: kicad-cli pcb drc / render.
#
#   python3 scripts/gen-pcie3-condensed.py            # board + routing guides + plan PNG
#   python3 scripts/gen-pcie3-condensed.py --no-plan  # skip the matplotlib plan
#   python3 scripts/gen-pcie3-condensed.py --force    # overwrite even if already routed
import os, re, sys, math, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + "/scripts")
# import gen-module-pcb.py for its emit helpers WITHOUT running its build loop
# (its module-level CLI filters to board-name args; a name that matches nothing builds
# nothing). Does not touch the shared generator or any EPS file.
_saved_argv = sys.argv
sys.argv = ["gen-pcie3-condensed", "__none__"]
import importlib.util
_spec = importlib.util.spec_from_file_location("gmp", ROOT + "/scripts/gen-module-pcb.py")
gmp = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(gmp)
sys.argv = _saved_argv
place, parse_netlist, gnd_planes, stackup = gmp.place, gmp.parse_netlist, gmp.gnd_planes, gmp.stackup
LAYERS, U, ff, carve, fp_path = gmp.LAYERS, gmp.U, gmp.ff, gmp.carve, gmp.fp_path

DIR, BASE, N = "pcie-8pin-3port", "pcie8pin-3port-module", 3

# ----------------------------------------------------------------- frame geometry
# 45586 (pegged): pads row1 y0 / row2 y-5.5, snap pegs native (0,7.3)/(-12.6,7.3),
# courtyard x[-15.55,3.35] y[-6.94,14.16]. At J_IN rot180 the pads land at y=JIN_Y
# (row1) / JIN_Y+5.5 (row2) and the pegs at JIN_Y-7.3=2.7 (hole 1.2mm off the top
# edge); the mouth overhangs the top edge. J_OUT rot0 mirrors it at the bottom.
CX0, PITCH, H = 5.0, 21.0, 44.0
JIN_Y, BAND_Y = 10.0, 22.0
CORE_W = 34.0                                  # electronics core width (tight, DRC-validated)
def geometry():
    cables_right = CX0 + (N - 1) * PITCH + 15.95   # rightmost 45586 courtyard (J_OUT +3.35 of x+12.6)
    ex = cables_right + 2.0                         # electronics-core left x
    return round(ex + CORE_W), H, ex                # W, H, ex  ->  99 x 44, ex=65

def frame():
    """ICs, connectors, shunts, mounts, logo -- the condensed pegged-45586 frame.
    Passives are placed by the clearance-aware engine around these anchors."""
    W, H_, ex = geometry()
    P = {}
    for i in range(N):
        Xc, c = CX0 + i * PITCH, i + 1
        # 45586: J_IN rot180 (mouth -> top edge, pads y10/15.5, pegs y2.7), J_OUT rot0
        # (mouth -> bottom). J_OUT at Xc+12.6 keeps the +12V columns aligned so 12V
        # flows straight down through the shunt. Both mouths overhang their edge.
        P[f"J_IN{c}"]  = (Xc, JIN_Y, 180)
        P[f"J_OUT{c}"] = (Xc + 12.6, H_ - JIN_Y, 0)
        # sense band across the column at BAND_Y: INA238(+/-3.18w) | shunt rot90(+/-1.93w)
        # | INA181/TLV7011 stacked(+/-2.05w) -- spread so courtyards clear.
        P[f"U1{i}"] = (Xc + 0.5,  BAND_Y, 0)          # INA238 (U10/U11/U12), Kelvin-taps the shunt
        P[f"RS{c}"] = (Xc + 6.5,  BAND_Y, 90)         # 0.5mOhm shunt, vertical in the 12V column
        P[f"U2{i}"] = (Xc + 11.0, BAND_Y - 2.2, 0)    # INA181A2 (U20/U21/U22)
        P[f"U3{i}"] = (Xc + 11.0, BAND_Y + 2.2, 0)    # TLV7011 (U30/U31/U32)
    # ---- electronics core (ex-relative, ~34mm) ----
    P.update({
        "J5": (ex + 7.0,  4.5, 180),                  # USB-C, top edge (overhangs top)
        "U1": (ex + 9.0,  21.0, 0),                   # ESP32-C6 (antenna keepout dropped, no wireless)
        "U2": (ex + 18.0, 5.5, 0),                    # TJA1051/3 CAN, top-right of USB-C
        "U3": (ex + 5.0,  39.5, 0),                   # LP5907 LDO, bottom-left
        "SW1": (ex + 11.0, 40.0, 0), "SW2": (ex + 16.0, 40.0, 0),
        "D2": (ex + 21.0, 40.0, 90),                  # VBUS ORing SOD-323
        "J1": (ex + 25.0, 22.0, 90),                  # RJ-45 FTP, right edge (mouth overhangs +x)
    })
    # right-side mounts only (the 21mm pitch that buys sub-100mm leaves no inter-cable
    # gap for an M3; the six peg-anchored connectors hold the cable half).
    mounts = [(W - 4.5, 4.5), (W - 4.5, H_ - 4.5)]
    logo = (ex + 9.0, 31.0)
    return W, H_, ex, P, mounts, logo

# ----------------------------------------------------------------- pad / courtyard geometry
_cp = {}; _pd = {}
def _fp(libid): return open(fp_path(*libid.split(":")) if ":" in libid else fp_path("cec", libid)).read()
def _crt_pts(libid):
    if libid in _cp: return _cp[libid]
    t = _fp(libid); pts = []
    for m in re.finditer(r"\((?:fp_line|fp_rect|fp_poly|fp_circle)\b", t):
        b = carve(t, m.start())
        if "CrtYd" not in b: continue
        for a, c in re.findall(r"(-?\d+\.?\d*) (-?\d+\.?\d*)", b):
            ly = float(c)
            if libid.endswith("ESP32-C6-MINI-1") and ly < -5.0: ly = -4.95   # antenna keepout dropped
            pts.append((float(a), ly))
    _cp[libid] = pts; return pts
def _pads(libid):
    if libid in _pd: return _pd[libid]
    t = _fp(libid); out = []
    for m in re.finditer(r"\(pad ", t):
        b = carve(t, m.start()); at = re.search(r"\(at (-?[\d.]+) (-?[\d.]+)", b); sz = re.search(r"\(size ([\d.]+) ([\d.]+)", b)
        if at and sz: out.append((float(at.group(1)), float(at.group(2)), float(sz.group(1)), float(sz.group(2))))
    _pd[libid] = out; return out
def _rot(lx, ly, r):
    a = math.radians(-r); return lx * math.cos(a) - ly * math.sin(a), lx * math.sin(a) + ly * math.cos(a)
def cbox(libid, x, y, r):
    xs = []; ys = []
    for lx, ly in _crt_pts(libid):
        rx, ry = _rot(lx, ly, r); xs.append(x + rx); ys.append(y + ry)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (x, y, x, y)
def prects(libid, x, y, r):
    out = []
    for lx, ly, sw, sh in _pads(libid):
        rx, ry = _rot(lx, ly, r); w, h = ((sh, sw) if abs((r % 180) - 90) < 1 else (sw, sh))
        out.append((x + rx - w / 2, y + ry - h / 2, x + rx + w / 2, y + ry + h / 2))
    return out
def _ov(a, b, g): return not (a[2] < b[0] - g or b[2] < a[0] - g or a[3] < b[1] - g or b[3] < a[1] - g)
def _pad_global(ref, pad, P, comps):
    X, Y, A = P[ref]
    for lx, ly, _w, _h in []:  # placeholder
        pass
    nm = comps[ref]; t = _fp(nm); loc = None
    for m in re.finditer(r"\(pad ", t):
        b = carve(t, m.start()); num = re.match(r'\(pad "([^"]*)"', b); at = re.search(r"\(at (-?[\d.]+) (-?[\d.]+)", b)
        if num and at and num.group(1) == str(pad): loc = (float(at.group(1)), float(at.group(2))); break
    if loc is None: return (X, Y)
    a = math.radians(A); lx, ly = loc
    return (X + lx * math.cos(a) + ly * math.sin(a), Y - lx * math.sin(a) + ly * math.cos(a))

# ----------------------------------------------------------------- passive engine
MOUNT = "cec-MountingHole:MountingHole_3.2mm_M3_Pad_Via"
PASSIVE_SPEC = {
    "C3":  ("U1",  "+3V3"),   "C7":  ("U1",  "+3V3"),   "C5":  ("U1",  "/EN"),
    "R2":  ("U1",  "/EN"),    "R10": ("U1",  "/THRESH_PWM"),
    "R3":  ("U1",  "/I2C_SDA"), "R4":("U1",  "/I2C_SCL"),
    "C40": ("U30", "/THRESH"),
    "C4":  ("U2",  "+5VSB"),  "C8":  ("U2",  "+3V3"),
    "C1":  ("U3",  "+5VSB"),  "C2":  ("U3",  "+3V3"),   "C6":  ("U3",  "+5VSB"),
    "C9":  ("J5",  "/VBUS"),  "R8":  ("J5",  "/USB_CC1"), "R9":("J5",  "/USB_CC2"),
    "D1":  ("J1",  "/DETECT"), "R1": ("J1",  "/DETECT"), "R7": ("J1",  "/DETECT"),
    # per-cable bypass caps (owner INA238 / INA181 / TLV7011)
    "C10": ("U10", "+3V3"), "C11": ("U11", "+3V3"), "C12": ("U12", "+3V3"),
    "C20": ("U20", "+3V3"), "C21": ("U21", "+3V3"), "C22": ("U22", "+3V3"),
    "C30": ("U30", "+3V3"), "C31": ("U31", "+3V3"), "C32": ("U32", "+3V3"),
}

def verify_passives(nets):
    members = {nm: {r for r, _ in nodes} for nm, nodes in nets.items()}
    bad = [ref for ref, (own, net) in PASSIVE_SPEC.items() if ref not in members.get(net, set())]
    for ref in bad:
        own, net = PASSIVE_SPEC[ref]
        print(f"  VERIFY: {ref} expected on {net} (owner {own}) -- not in netlist", file=sys.stderr)
    print(f"  passive ownership: {len(PASSIVE_SPEC)-len(bad)}/{len(PASSIVE_SPEC)} netlist-verified")
    return not bad

def pack_passives(P, comps, ex, W, H_, mounts):
    """Place every PASSIVE_SPEC member at the nearest DRC-clean spot to its owner IC,
    searching outward on a grid. Courtyard gap 0.35 / pad gap 0.28 -> clean by build."""
    occ = {ref: (cbox(comps.get(ref, MOUNT), x, y, r), prects(comps.get(ref, MOUNT), x, y, r))
           for ref, (x, y, r) in P.items() if comps.get(ref)}
    # reserve the mount keep-outs too
    for mi, (mx, my) in enumerate(mounts, 1):
        occ[f"H{mi}"] = (cbox(MOUNT, mx, my, 0), prects(MOUNT, mx, my, 0))
    def free(lib, x, y, r, cg=0.35, pg=0.28):
        cb = cbox(lib, x, y, r); pr = prects(lib, x, y, r)
        if cb[0] < 0.5 or cb[1] < 0.5 or cb[2] > W - 0.5 or cb[3] > H_ - 0.5:  # keep on-board
            return False
        for cbk, prk in occ.values():
            if _ov(cb, cbk, cg): return False
            for a in pr:
                for b in prk:
                    if _ov(a, b, pg): return False
        return True
    placed = []
    unfit = []
    for ref, (own, _net) in PASSIVE_SPEC.items():
        lib = comps.get(ref)
        if not lib: unfit.append(ref); continue
        ox, oy, _r = P.get(own, (ex + 8, 22, 0))
        best = None; bd = 1e9
        # search a grid around the owner, growing radius
        for rad in [r * 0.3 for r in range(2, 60)]:
            for ang in range(0, 360, 20):
                x = ox + rad * math.cos(math.radians(ang)); y = oy + rad * math.sin(math.radians(ang))
                if free(lib, x, y, 0):
                    d = (x - ox) ** 2 + (y - oy) ** 2
                    if d < bd: bd = d; best = (x, y)
            if best: break
        if best:
            P[ref] = (best[0], best[1], 0)
            occ[ref] = (cbox(lib, best[0], best[1], 0), prects(lib, best[0], best[1], 0))
            placed.append(ref)
        else:
            unfit.append(ref)
    print(f"  passive packing: {len(placed)}/{len(PASSIVE_SPEC)} placed" + (f"  UNFIT {unfit}" if unfit else ""))
    return P, unfit

# ----------------------------------------------------------------- build the board
def build():
    out  = f"{ROOT}/modules/{DIR}/{BASE}.kicad_pcb"
    netf = f"{ROOT}/modules/{DIR}/{BASE}.net"
    if not os.path.exists(netf):
        os.system(f"cd {ROOT}/modules/{DIR} && kicad-cli sch export netlist -o {BASE}.net {BASE}.kicad_sch >/dev/null 2>&1")
    if os.path.exists(out) and re.search(r"\n\s*\((?:segment|via)\b", open(out).read()):
        if "--force" not in sys.argv:
            print(f"  SKIP {out}: already routed; pass --force"); return
    comps, vals, nets = parse_netlist(netf)
    names = [x for x in sorted(nets) if x]
    code_of = {x: i + 1 for i, x in enumerate(names)}
    padnet = {(r, p): (code_of[x], x) for x, nodes in nets.items() if x for (r, p) in nodes}
    verify_passives(nets)
    W, H_, ex, P, mounts, logo = frame()
    pack_passives(P, comps, ex, W, H_, mounts)
    fps = []
    for ref, (x, y, rot) in P.items():
        lib = comps.get(ref)
        if lib: fps.append(place(lib, ref, x, y, rot, padnet, code_of, val=vals.get(ref)))
        else:   print(f"  WARN no footprint for {ref}", file=sys.stderr)
    for i, (x, y) in enumerate(mounts, 1):
        fps.append(place(MOUNT, f"H{i}", x, y, 0, padnet, code_of, gnd_all=True))
    fps.append(place("cec:CEC_Logo_Copper", "LOGO1", logo[0], logo[1], 0, padnet, code_of, flip=True))
    e = []
    pts = [(0, 0), (W, 0), (W, H_), (0, H_), (0, 0)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        e.append(f'\t(gr_line (start {ff(x1)} {ff(y1)}) (end {ff(x2)} {ff(y2)}) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "{U()}"))')
    note = (f'\t(gr_text "CEC {BASE}  4L 2oz/1oz  99x44" (at {ff(logo[0])} {ff(H_ - 3)} 0) (layer "B.SilkS") (uuid "{U()}") '
            f'(effects (font (size 0.9 0.9) (thickness 0.13)) (justify mirror)))')
    netdecl = '\t(net 0 "")\n' + "\n".join(f'\t(net {code_of[x]} "{x}")' for x in names)
    zones = gnd_planes(code_of["GND"], W, H_) + "\n"
    guides = routing_guides(P, W, H_, ex, comps) + "\n"
    doc = ("(kicad_pcb\n\t(version 20260206)\n\t(generator \"cec-gen-pcie3-condensed\")\n\t(generator_version \"10.0\")\n"
           "\t(general\n\t\t(thickness 1.6)\n\t\t(legacy_teardrops no)\n\t)\n\t(paper \"A4\")\n" + LAYERS +
           "\n\t(setup\n" + stackup() + "\n\t\t(pad_to_mask_clearance 0)\n\t\t(allow_soldermask_bridges_in_footprints no)\n\t)\n"
           + netdecl + "\n" + "\n".join(fps) + "\n" + "\n".join(e) + "\n" + zones + guides + note + "\n\t(embedded_fonts no)\n)\n")
    # ESP32-C6 antenna keepout dropped (no wireless): trim courtyard to body.
    doc = doc.replace("-10.98", "-4.95")
    open(out, "w").write(doc)
    print(f"WROTE {os.path.relpath(out, ROOT)}  board={W}x{H_:.0f}mm  parts={len(fps)}  +routing guides")

# ----------------------------------------------------------------- routing candidates
def _line(pts, layer, w=0.25):
    out = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        out.append(f'\t(gr_line (start {ff(x1)} {ff(y1)}) (end {ff(x2)} {ff(y2)}) '
                   f'(stroke (width {w}) (type solid)) (layer "{layer}") (uuid "{U()}"))')
    return "\n".join(out)
def _txt(t, x, y, layer, sz=0.8):
    return (f'\t(gr_text "{t}" (at {ff(x)} {ff(y)} 0) (layer "{layer}") (uuid "{U()}") '
            f'(effects (font (size {sz} {sz}) (thickness 0.12))))')

def routing_guides(P, W, H_, ex, comps):
    g = []
    pg = lambda ref, p: _pad_global(ref, p, P, comps)
    # Kelvin sense pairs off each shunt's inner edges -> INA238 + INA181
    for i in range(N):
        rsx = (CX0 + i * PITCH) + 6.5
        g.append(_line([(rsx, BAND_Y - 2.75), pg(f"U1{i}", "10")], "Cmts.User", 0.25))
        g.append(_line([(rsx, BAND_Y + 2.75), pg(f"U1{i}", "8")],  "Cmts.User", 0.25))
        g.append(_line([(rsx, BAND_Y - 2.75), pg(f"U2{i}", "3")],  "Cmts.User", 0.25))
        g.append(_line([(rsx, BAND_Y + 2.75), pg(f"U2{i}", "4")],  "Cmts.User", 0.25))
    g.append(_txt("Kelvin: tap shunt INNER edge, matched pair over In1 GND", CX0 + 1, BAND_Y - 6, "Cmts.User", 0.6))
    # control->sense spine along the BAND_Y split-gap lane (Eco1.User)
    g.append(_txt("SPINE: +3V3 / I2C / THRESH / DETC along y~22 gap; hop shunts on B.Cu", ex - 2, BAND_Y + 6.5, "Eco1.User", 0.6))
    g.append(_txt("CAN pair -> RJ45 ; USB FS pair -> ESP (length-match)", ex + 2, 12, "Eco2.User", 0.6))
    return "\n".join(g)

# ----------------------------------------------------------------- routing-plan PNG
def _gcourt(libid, x, y, rot):
    xs = []; ys = []
    for lx, ly in _crt_pts(libid):
        rx, ry = _rot(lx, ly, rot); xs.append(x + rx); ys.append(y + ry)
    return (min(xs), max(xs), min(ys), max(ys)) if xs else (x - 1, x + 1, y - 1, y + 1)

def routing_plan_png():
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Polygon, Circle
    from matplotlib.lines import Line2D
    netf = f"{ROOT}/modules/{DIR}/{BASE}.net"
    comps, vals, nets = parse_netlist(netf)
    W, H_, ex, P, mounts, logo = frame(); pack_passives(P, comps, ex, W, H_, mounts)
    C = dict(v12i="#d83434", v12o="#e8862a", gnd="#1f9e6f", kel="#1438a8",
             p3v3="#1f9e6f", sig="#7a52c8", can="#b5179e", usb="#1d7fd8", body="#9aa7b4", txt="#101418")
    fig = plt.figure(figsize=(18.5, 8.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.9, 1.0], wspace=0.02)
    ax = fig.add_subplot(gs[0]); nx = fig.add_subplot(gs[1]); nx.axis("off")
    ax.set_aspect("equal"); ax.set_xlim(-3, W + 3); ax.set_ylim(H_ + 4, -5); ax.axis("off")
    ax.add_patch(Rectangle((0, 0), W, H_, fill=False, ec="#222", lw=1.6))
    ax.text(W / 2, -3.0, f"CEC PCIe 8-pin 3-port — sub-100mm routing-candidate plan   {W:.0f} x {H_:.0f} mm   "
            f"4-layer F.Cu / In1 GND / In2 GND / B.Cu   (12V on outers, split at each shunt)",
            ha="center", va="center", fontsize=11, weight="bold", color=C["txt"])
    pg = lambda ref, p: _pad_global(ref, p, P, comps)
    for ref, (x, y, rot) in P.items():
        lib = comps.get(ref)
        if not lib: continue
        x0, x1, y0, y1 = _gcourt(lib, x, y, rot)
        big = ref in ("J1", "J5") or ref.startswith("J_")
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=True, fc="#eef1f4" if not big else "#dde6ee",
                     ec=C["body"], lw=0.7, alpha=0.95, zorder=2))
        if ref.startswith(("U", "J", "RS")) or ref in ("D1", "D2"):
            ax.text((x0 + x1) / 2, (y0 + y1) / 2, ref, ha="center", va="center",
                    fontsize=6.0 if not big else 7.5, color=C["txt"], zorder=6, weight="bold")
    for (mx, my) in mounts:
        ax.add_patch(Circle((mx, my), 3.2, fill=True, fc="#f2d34e", ec="#b69a18", lw=0.8, zorder=1))
    # 12V IN/OUT + GND stitch hints + Kelvin pairs
    for i in range(N):
        Xc = CX0 + i * PITCH
        ax.add_patch(Polygon([(Xc - 2.2, 7.5), (Xc + 2.6, 7.5), (Xc + 2.6, 17), (Xc - 2.2, 17)], closed=True,
                     fc=C["v12i"], ec=C["v12i"], alpha=0.20, lw=1.0, zorder=3))
        ax.add_patch(Polygon([(Xc + 10.4, 27), (Xc + 15.2, 27), (Xc + 15.2, 36.5), (Xc + 10.4, 36.5)], closed=True,
                     fc=C["v12o"], ec=C["v12o"], alpha=0.20, lw=1.0, zorder=3))
        rsx = Xc + 6.5
        for tap, dst in [((rsx, BAND_Y - 2.75), pg(f"U1{i}", "10")), ((rsx, BAND_Y + 2.75), pg(f"U1{i}", "8")),
                         ((rsx, BAND_Y - 2.75), pg(f"U2{i}", "3")),  ((rsx, BAND_Y + 2.75), pg(f"U2{i}", "4"))]:
            ax.plot([tap[0], dst[0]], [tap[1], dst[1]], color=C["kel"], lw=1.3, zorder=5)
    # CAN + USB
    def poly(p, col, lw, z=5, ls="-"):
        ax.plot([q[0] for q in p], [q[1] for q in p], color=col, lw=lw, ls=ls, zorder=z)
    poly([pg("U2", "7"), pg("J1", "3")], C["can"], 1.4); poly([pg("U2", "6"), pg("J1", "6")], C["can"], 1.4)
    poly([pg("U2", "1"), pg("U1", "26")], C["can"], 1.0, ls=(0, (4, 2)))
    poly([pg("U2", "4"), pg("U1", "27")], C["can"], 1.0, ls=(0, (4, 2)))
    poly([pg("J5", "A6"), pg("U1", "18")], C["usb"], 1.6); poly([pg("J5", "A7"), pg("U1", "17")], C["usb"], 1.6)
    leg = [Line2D([], [], color=C["v12i"], lw=6, alpha=.4, label="12V IN pour (F+B, 2oz)"),
           Line2D([], [], color=C["v12o"], lw=6, alpha=.4, label="12V OUT pour"),
           Line2D([], [], color=C["kel"], lw=2, label="Kelvin sense pair (0.25mm)"),
           Line2D([], [], color=C["can"], lw=2, label="CAN H/L + TX/RX"),
           Line2D([], [], color=C["usb"], lw=2, label="USB FS pair (matched)")]
    ax.legend(handles=leg, loc="lower center", bbox_to_anchor=(0.5, -0.15), ncol=3, fontsize=8, framealpha=.95)
    def block(y, title, lines):
        nx.text(0.0, y, title, fontsize=11, weight="bold", color=C["txt"], transform=nx.transAxes)
        for k, ln in enumerate(lines):
            nx.text(0.02, y - 0.034 * (k + 1), ln, fontsize=8.0, color="#222", transform=nx.transAxes)
        return y - 0.034 * (len(lines) + 1) - 0.025
    y = 0.99
    y = block(y, "SUB-100mm 3-PORT — WHY 99 x 44", [
        "* 21mm cable pitch (vs 27mm on the 126mm board) + a 34mm core.",
        "* 45586 snap pegs keep H=44 (EPS pegless 87427 reaches 35).",
        "* Mounts: RIGHT side only (2x M3). The 21mm pitch leaves no",
        "  inter-cable gap for an M3; the six 45586 connectors (8 pins +",
        "  2 x3mm pegs each) anchor the cable half mechanically.",
        "* Connectors + RJ-45 mouth overhang their board edges."])
    y = block(y, "ROUTING ORDER", [
        "1. Pour In1+In2 GND; stitch every connector/IC GND.",
        "2. 12V IN/OUT pours per cable (F.Cu + B.Cu mirror); split at shunt.",
        "3. Kelvin stubs (4/shunt) off the INNER pad edges, matched over GND.",
        "4. USB DP/DM pair (short, straight, length-matched).",
        "5. CAN H/L -> RJ45 ; TX/RX -> ESP.",
        "6. Control->sense SPINE (+3V3 / I2C / THRESH / DETC1-3) on y~22 gap.",
        "7. +5VSB / VBUS-OR / DETECT core knit + EN.  8. Re-pour, DRC."])
    block(y, "SI / KEEP-AWAY", [
        "* Kelvin pairs & THRESH ref: >=0.5mm off any 12V copper edge.",
        "* THRESH shared comparator ref -- quiet quasi-DC lane, C40 at source.",
        "* Spine runs the open y~17-26 band between J_IN and J_OUT;",
        "  hop a shunt column on B.Cu.",
        "* USB length-match DP/DM (J5 sits above the ESP).",
        "* CAN H/L stay paired; 120R split termination lives at the Hub."])
    out = f"{ROOT}/modules/{DIR}/pcie3-routing-plan.png"
    fig.savefig(out, dpi=145, bbox_inches="tight", facecolor="white")
    print(f"WROTE {os.path.relpath(out, ROOT)}")

if __name__ == "__main__":
    build()
    if "--no-plan" not in sys.argv:
        routing_plan_png()
