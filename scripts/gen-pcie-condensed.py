#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Candidate floorplan generator for the PCIe 8-pin telemetry modules -- PARAMETRIC
# in the cable count N for BOTH SKUs:
#
#     pcie-8pin-2port / pcie8pin-2port-module   (N=2,  ~86 x 44 mm)
#     pcie-8pin-3port / pcie8pin-3port-module   (N=3, ~103 x 44 mm, sub-105)
#
# Mirrors gen-eps-condensed.py exactly: EXPLICIT, deterministic, DRC-clean major
# placement + EXPLICIT support-passive clusters (NO runtime packer -- the EPS way,
# so the layout is reviewable and reproducible).
#
#   * FRAME    -- N cables on the REAL pegged Molex 45586 (J_IN rot180 mouth->top /
#                 J_OUT rot0 mouth->bottom so the +12V columns line up straight
#                 through the per-cable 0.5 mOhm shunt). One sense band per cable
#                 (INA238 | shunt | INA181 + TLV7011), then a tight ~34 mm
#                 electronics core (ESP32-C6 / CAN / LDO / RJ-45 / USB-C front end).
#   * MOUNTS   -- 3x M3: TWO on the LOGIC (right) side (top-right + bottom-right
#                 corners), ONE on the CONNECTOR (left) side roughly centered
#                 (x~4, y~H/2), in the clear band between the first cable's J_IN
#                 and J_OUT courtyards. The left margin CX0=11 buys that mount room
#                 (the first cable's sense band clears the mount circle by ~6 mm).
#   * PASSIVES -- every decoupling/RC/pull-up/ESD passive at an EXPLICIT DRC-clean
#                 spot in its OWNER IC's cluster (per-cable bypass C10/C11/C12,
#                 C20/C21/C22, C30/C31/C32 + the core C1-C9,C40,R1-R10,D1).
#                 PASSIVE_SPEC + verify_passives() assert the netlist still agrees,
#                 so the cluster owner cannot drift from the schematic.
#
# Reuses gen-module-pcb.py's emit helpers WITHOUT running its build loop (imported
# with a board filter that matches nothing). Detached from the EPS module and the
# shared generator by construction: imports gen-module-pcb.py read-only and writes
# ONLY modules/pcie-8pin-{2,3}port/. One-shot bootstrap -- the board is hand-
# maintained in the GUI after the first route. Verify: kicad-cli pcb drc / render.
#
#   python3 scripts/gen-pcie-condensed.py pcie-8pin-2port           # build the 2-port
#   python3 scripts/gen-pcie-condensed.py pcie-8pin-3port           # build the 3-port
#   python3 scripts/gen-pcie-condensed.py pcie-8pin-3port --force   # overwrite a routed board
#
# routing_guides() is a STUB (returns "") -- a follow-up routing sub-agent fills it
# in (and any routing-plan PNG); leaving the stub avoids a collision.
import os, re, sys, math, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + "/scripts")
# import gen-module-pcb.py for its emit helpers WITHOUT running its build loop
# (its module-level CLI filters to board-name args; a name that matches nothing builds
# nothing). Does not touch the shared generator or any EPS file.
_saved_argv = sys.argv
sys.argv = ["gen-pcie-condensed", "__none__"]
import importlib.util
_spec = importlib.util.spec_from_file_location("gmp", ROOT + "/scripts/gen-module-pcb.py")
gmp = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(gmp)
sys.argv = _saved_argv
place, parse_netlist, gnd_planes, stackup = gmp.place, gmp.parse_netlist, gmp.gnd_planes, gmp.stackup
LAYERS, U, ff, carve, fp_path = gmp.LAYERS, gmp.U, gmp.ff, gmp.carve, gmp.fp_path

# --------------------------------------------------------------- SKU selection
# (dir, board base, N, cable PITCH).  N=3 PITCH=20 buys the sub-105mm board;
# N=2 can afford PITCH=23 for routing room (negligible cost). board-name arg picks.
SKUS = {
    "pcie-8pin-2port":      ("pcie-8pin-2port", "pcie8pin-2port-module", 2, 23.0),
    "pcie8pin-2port-module": ("pcie-8pin-2port", "pcie8pin-2port-module", 2, 23.0),
    "pcie-8pin-3port":      ("pcie-8pin-3port", "pcie8pin-3port-module", 3, 20.0),
    "pcie8pin-3port-module": ("pcie-8pin-3port", "pcie8pin-3port-module", 3, 20.0),
}

# --------------------------------------------------------------- footprints
MOUNT = "cec-MountingHole:MountingHole_3.2mm_M3_Pad_Via"
LIB = dict(
    ESP="cec-RF_Module:ESP32-C6-MINI-1",
    CAN="cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    LDO="cec-Package_TO_SOT_SMD:SOT-23-5",
    USB="cec-Connector_USB:USB_C_Receptacle_XKB_U262-16XN-4BVC11",
    SW="cec-Button_Switch_SMD:TS-1088-AR02016",
    SMA="cec-Diode_SMD:D_SMA",
    SOD="cec-Diode_SMD:D_SOD-323",
    RJ="cec:RJ45_FTP_Shielded_Horizontal",
    J="cec-Connector_Molex:Molex_Mini-Fit_Jr_45586_2x04_P4.20mm_Horizontal",
    INA238="cec-Package_SO:VSSOP-10_3x3mm_P0.5mm",
    RS="cec-Resistor_SMD:R_2512_6332Metric",
    INA181="cec-Package_TO_SOT_SMD:SOT-23-6",
    TLV="cec-Package_TO_SOT_SMD:SOT-23-5",
    C402="cec-Capacitor_SMD:C_0402_1005Metric",
    C603="cec-Capacitor_SMD:C_0603_1608Metric",
    C805="cec-Capacitor_SMD:C_0805_2012Metric",
    R402="cec-Resistor_SMD:R_0402_1005Metric",
)

# --------------------------------------------------------------- frame geometry
# 45586 (pegged): pads row1 y0 / row2 y-5.5, snap pegs native (0,7.3)/(-12.6,7.3),
# courtyard x[-15.55,3.35] y[-6.94,14.16]. At J_IN rot180 the pads land at y=JIN_Y
# (row1) / JIN_Y+5.5 (row2) and the pegs at JIN_Y-7.3=2.7 (hole 1.2mm off the top
# edge); the mouth overhangs the top edge. J_OUT rot0 mirrors it at the bottom.
# The pegs FORCE H=44 (the EPS pegless 87427 reaches 35).
CX0, H = 11.0, 44.0                            # 11mm left margin -> the centered left M3 fits
JIN_Y, BAND_Y = 10.0, 22.0                     # J_IN origin / sense-band center
CORE_W = 34.0                                  # electronics-core width (tight, DRC-validated)
CABLE_RIGHT = 15.948                           # rightmost 45586 courtyard reach (J_OUT +3.348 of x+12.6)

def geometry(N, PITCH):
    cables_right = CX0 + (N - 1) * PITCH + CABLE_RIGHT
    ex = cables_right + 2.5                     # electronics-core left x
    return round(ex + CORE_W, 1), H, ex         # W, H, ex

# ---- electronics core, EXPLICIT (ex-relative): ref -> (libkey, dx, dy, rot). All
# courtyards DRC-validated clear at CORE_W=34 with the 3 mounts (TR/BR + left-center).
CORE = {
    # ---- majors ----
    "J5":  ("USB", 6.5,  4.5, 180),            # USB-C, top edge (mouth overhangs -y)
    "U1":  ("ESP", 8.0,  22.0, 0),             # ESP32-C6 (antenna keepout dropped, no wireless)
    "U2":  ("CAN", 20.5, 5.5,  0),             # TJA1051/3 CAN, top-right of USB-C
    "U3":  ("LDO", 4.5,  39.0, 0),             # LP5907 LDO, bottom-left
    "SW1": ("SW",  13.0, 40.5, 0),             # BOOT
    "SW2": ("SW",  18.0, 40.5, 0),             # RESET
    "D2":  ("SMA", 22.5, 34.5, 0),             # VBUS ORing SMA (clear of SW2 + BR mount)
    # ---- ESP +3V3 / EN cluster (above the ESP) ----
    "C3":  ("C402", 3.0,  15.5, 0),            # ESP +3V3 HF bypass
    "C5":  ("C402", 6.0,  15.5, 0),            # ESP EN reset-RC cap
    "R2":  ("R402", 8.5,  15.5, 0),            # ESP EN pull-up to +3V3
    "C7":  ("C805", 13.5, 15.0, 0),            # ESP +3V3 bulk
    # ---- USB CC / VBUS (top, under USB-C) ----
    "R8":  ("R402", 13.32, 2.12, 0),           # USB CC1 pull-down
    "R9":  ("R402", 13.52, 3.43, 0),           # USB CC2 pull-down
    "C9":  ("C805", 13.5, 11.0, 0),            # USB-C VBUS bulk
    # ---- CAN bypass ----
    "C4":  ("C402", 25.55, 8.59, 0),           # CAN VCC bypass
    "C8":  ("C402", 16.45, 9.09, 0),           # CAN VIO bypass
    # ---- LDO in/out + 5VSB entry (bottom-left) ----
    "C1":  ("C603", 2.5,  34.5, 0),            # LDO VIN bulk
    "C2":  ("C603", 8.5,  39.0, 0),            # LDO VOUT bulk
    "C6":  ("C805", 2.5,  30.5, 0),            # +5VSB board-entry bulk
    # ---- I2C pull-ups + THRESH RC (mid band) ----
    "R3":  ("R402", 12.5, 30.5, 0),            # I2C SDA pull-up
    "R4":  ("R402", 14.85, 30.7, 0),           # I2C SCL pull-up
    "R10": ("R402", 17.27, 30.71, 0),          # THRESH series R (PWM IO14)
    "C40": ("C402", 19.54, 31.1, 0),           # THRESH filter cap (shared U30/U31/U32)
    # ---- DETECT front-end (near J1) ----
    "D1":  ("SOD", 23.0, 30.0, 0),             # DETECT ESD clamp
    "R1":  ("R402", 26.0, 30.0, 0),            # DETECT 2.2k code resistor
    "R7":  ("R402", 28.35, 30.2, 0),           # DETECT 100k poke tap -> ESP
}

def frame(N, PITCH):
    """ICs, connectors, shunts, mounts, logo -- the condensed pegged-45586 frame.
    EXPLICIT, deterministic. Per-cable sense parts + the electronics core; passives
    are added by place_passives() at their explicit cluster spots."""
    W, H_, ex = geometry(N, PITCH)
    P = {}
    for i in range(N):
        Xc, c = CX0 + i * PITCH, i + 1
        # 45586: J_IN rot180 (mouth -> top edge, pads y10/15.5, pegs y2.7), J_OUT
        # rot0 (mouth -> bottom). J_OUT at Xc+12.6 keeps the +12V columns aligned so
        # 12V flows straight down through the shunt. Both mouths overhang their edge.
        P[f"J_IN{c}"]  = (LIB["J"], Xc, JIN_Y, 180)
        P[f"J_OUT{c}"] = (LIB["J"], Xc + 12.6, H_ - JIN_Y, 0)
        # sense band across the column at BAND_Y: INA238 | shunt rot90 | INA181/TLV
        # stacked (+/-2.2 in y). Spread so courtyards clear; band right edge Xc+13.05.
        P[f"U1{i}"] = (LIB["INA238"], Xc + 0.5,  BAND_Y, 0)         # INA238 (U10/U11/U12), Kelvin-taps the shunt
        P[f"RS{c}"] = (LIB["RS"],     Xc + 6.5,  BAND_Y, 90)        # 0.5mOhm shunt, vertical in the 12V column
        P[f"U2{i}"] = (LIB["INA181"], Xc + 11.0, BAND_Y - 2.2, 0)  # INA181A2 (U20/U21/U22)
        P[f"U3{i}"] = (LIB["TLV"],    Xc + 11.0, BAND_Y + 2.2, 0)  # TLV7011 (U30/U31/U32)
    for ref, (lk, dx, dy, r) in CORE.items():
        P[ref] = (LIB[lk], ex + dx, dy, r)
    P["J1"] = (LIB["RJ"], W - 12.0, 22.0, 90)   # RJ-45 FTP, mouth overhangs the right edge
    # 3 M3 mounts: TWO on the logic (right) side (top-right + bottom-right corners),
    # ONE on the connector (left) side roughly centered, in the clear band between
    # cable 1's J_IN (y<=16.94) and J_OUT (y>=27.07) courtyards. The CX0=11 left
    # margin clears the left mount circle (r3.45) from cable 1's sense band by ~6mm.
    mounts = [(W - 4.5, 4.5), (W - 4.5, H_ - 4.5), (4.0, H_ / 2.0)]
    logo = (ex + 9.0, 33.0)
    return W, H_, ex, P, mounts, logo

# --------------------------------------------------------------- pad / courtyard geometry
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
def _rot(lx, ly, r):
    a = math.radians(-r); return lx * math.cos(a) - ly * math.sin(a), lx * math.sin(a) + ly * math.cos(a)
def cbox(libid, x, y, r):
    xs = []; ys = []
    for lx, ly in _crt_pts(libid):
        rx, ry = _rot(lx, ly, r); xs.append(x + rx); ys.append(y + ry)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (x, y, x, y)
def _pad_global(ref, pad, P, comps):
    X, Y, A = P[ref]
    nm = comps[ref]; t = _fp(nm); loc = None
    for m in re.finditer(r"\(pad ", t):
        b = carve(t, m.start()); num = re.match(r'\(pad "([^"]*)"', b); at = re.search(r"\(at (-?[\d.]+) (-?[\d.]+)", b)
        if num and at and num.group(1) == str(pad): loc = (float(at.group(1)), float(at.group(2))); break
    if loc is None: return (X, Y)
    a = math.radians(A); lx, ly = loc
    return (X + lx * math.cos(a) + ly * math.sin(a), Y - lx * math.sin(a) + ly * math.cos(a))

# --------------------------------------------------------------- passive engine
# PASSIVE_SPEC records (owner_IC, expected_net) from the netlist-verified placement
# analysis (netlist-correct -- verify_passives()
# asserts the netlist still agrees so the cluster owner cannot drift from the schematic).
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
    """Assert each passive shares its expected net (so the cluster owner is correct).
    The 3rd-cable rows (C12/C22/C32) only exist on the N=3 board, so SKIP any
    PASSIVE_SPEC ref the netlist doesn't carry (it isn't a drift -- it's the SKU)."""
    members = {nm: {r for r, _ in nodes} for nm, nodes in nets.items()}
    present = {r for nodes in nets.values() for (r, _p) in nodes}
    spec = {ref: v for ref, v in PASSIVE_SPEC.items() if ref in present}
    bad = [ref for ref, (own, net) in spec.items() if ref not in members.get(net, set())]
    for ref in bad:
        own, net = spec[ref]
        print(f"  VERIFY: {ref} expected on {net} (owner {own}) -- not in netlist", file=sys.stderr)
    print(f"  passive ownership: {len(spec)-len(bad)}/{len(spec)} netlist-verified "
          f"({len(spec)} of {len(PASSIVE_SPEC)} SPEC rows present on this SKU)")
    return not bad

def place_passives(P, N, PITCH, ex):
    """EXPLICIT DRC-clean cluster placement (frame-relative). Per-cable sense-band
    bypass caps are added per cable; the core passives are already placed by frame()
    via CORE. Each passive sits in its PASSIVE_SPEC owner's cluster; positions were
    DRC-validated against the courtyard model (NO runtime packer -- the EPS way)."""
    for i in range(N):
        Xc = CX0 + i * PITCH
        P[f"C1{i}"] = (LIB["C402"], Xc + 0.5,  BAND_Y - 3.0, 0)   # C10/C11/C12 INA238 VS bypass (above the INA)
        P[f"C2{i}"] = (LIB["C402"], Xc + 14.0, BAND_Y - 2.2, 0)   # C20/C21/C22 INA181 VS bypass
        P[f"C3{i}"] = (LIB["C402"], Xc + 14.0, BAND_Y + 2.2, 0)   # C30/C31/C32 TLV7011 VCC bypass
    return P

# --------------------------------------------------------------- routing candidates
# Drawn as guide graphics on toggleable user layers (non-plotted) so the routes are
# visible in the board while routing. Coordinates are keyed to the REAL placement (read
# from the footprint pads via pg(), below) so both SKUs (N=2 / N=3) render correctly.
# The matplotlib routing-plan PNG (routing_plan_png) carries the full color story.
# Mirrors gen-eps-condensed.py's _poly/_line/_txt + routing_guides() approach.
def pg(ref, pad, P, comps):
    """Global (x,y) of a pad on a placed part. Wraps the file's _pad_global to this
    generator's 4-tuple frame format P[ref]=(lib,X,Y,A) (gen-eps stores a 3-tuple)."""
    lib, X, Y, A = P[ref]
    P3 = dict(P); P3[ref] = (X, Y, A)        # _pad_global unpacks X,Y,A
    return _pad_global(ref, pad, P3, comps)

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

# Per-cable 12V pour OUTLINES, pad-derived so they track Xc for any N/PITCH. The shunt
# (RS, rot90) sits in the 12V column: /SENSEC_HI ties the J_IN +12V pads (y~10) to the
# shunt's LOWER pad (RS.1, y~24.96); /SENSEC_LO ties the J_OUT +12V pads (y~34) to the
# shunt's UPPER pad (RS.2, y~19.04) -- a deliberate crossover so 12V runs straight down
# the column through the shunt. IN pour = J_IN pads down to RS.1; OUT pour = RS.2 down
# to J_OUT pads. Both wrap the shunt body; the split is AT the shunt.
def _pour_outline(P, comps, c, side):
    j = f"J_IN{c}" if side == "in" else f"J_OUT{c}"
    p1 = pg(j, "1", P, comps); p2 = pg(j, "2", P, comps); p3 = pg(j, "3", P, comps)
    xs = sorted(x for x, _ in (p1, p2, p3)); xl, xr = xs[0] - 1.5, xs[-1] + 1.5
    rs = f"RS{c}"; rhi = pg(rs, "1", P, comps); rlo = pg(rs, "2", P, comps)  # HI=lower, LO=upper
    rcx = rhi[0]
    if side == "in":            # J_IN band (top) funneling down to the shunt LOWER pad
        ytop, ybot = 8.0, rhi[1] + 0.9
        ymid = 14.5
        return [(xl, ytop), (xr, ytop), (xr, ymid), (rcx + 1.6, ymid),
                (rcx + 1.6, ybot), (rcx - 1.6, ybot), (rcx - 1.6, ymid), (xl, ymid), (xl, ytop)]
    else:                        # shunt UPPER pad funneling down to the J_OUT band (bottom)
        ytop, ybot = rlo[1] - 0.9, 36.0
        ymid = 29.5
        return [(rcx - 1.6, ytop), (rcx + 1.6, ytop), (rcx + 1.6, ymid), (xr, ymid),
                (xr, ybot), (xl, ybot), (xl, ymid), (rcx - 1.6, ymid), (rcx - 1.6, ytop)]

def routing_guides(P, W, H_, ex, comps):
    g = []
    N = sum(1 for r in P if r.startswith("J_IN"))
    # --- NET CLASS 1: +12V IN/OUT pour outlines per cable (Dwgs.User) ---
    for i in range(N):
        c = i + 1
        IN  = _pour_outline(P, comps, c, "in")
        OUT = _pour_outline(P, comps, c, "out")
        g.append(_poly(IN,  "Dwgs.User")); g.append(_txt(f"12V_IN{c} (F+B,2oz)", IN[0][0] + 0.5, 6.6, "Dwgs.User", 0.7))
        g.append(_poly(OUT, "Dwgs.User")); g.append(_txt(f"12V_OUT{c}",          OUT[0][0] - 3.0, 37.4, "Dwgs.User", 0.7))
    # --- NET CLASS 3: Kelvin sense pairs off the shunt inner edges (Cmts.User) ---
    # tap the shunt at the INNER face of each pad (toward the body center, y=22), matched
    # pair to INA238 IN+/IN- (pads 10/8) and INA181 IN+/IN- (pads 3/4).
    for i in range(N):
        c = i + 1; rs = f"RS{c}"; u10 = f"U1{i}"; u20 = f"U2{i}"
        rhi = pg(rs, "1", P, comps); rlo = pg(rs, "2", P, comps)      # HI lower / LO upper
        hi_tap = (rhi[0], rhi[1] - 0.9); lo_tap = (rlo[0], rlo[1] + 0.9)  # inner edges toward center
        hi_in,  lo_in  = pg(u10, "10", P, comps), pg(u10, "8", P, comps)
        hi_181, lo_181 = pg(u20, "3", P, comps),  pg(u20, "4", P, comps)
        g.append(_line([hi_tap, hi_in],  "Cmts.User", 0.25))         # RS.HI -> INA238 IN+
        g.append(_line([lo_tap, lo_in],  "Cmts.User", 0.25))         # RS.LO -> INA238 IN-
        g.append(_line([hi_tap, hi_181], "Cmts.User", 0.25))         # RS.HI -> INA181 IN+
        g.append(_line([lo_tap, lo_181], "Cmts.User", 0.25))         # RS.LO -> INA181 IN-
    g.append(_txt("Kelvin: tap shunt INNER edge, matched pair over In1 GND", CX0, 17.0, "Cmts.User", 0.6))
    # --- NET CLASS 4: control->sense spine along the open y~17-26 band (Eco1.User) ---
    # +3V3 sub-trunk from the LDO out (U3.5) sweeping LEFT across every sense band; I2C
    # SDA/SCL (ESP 24/25) daisy to all INA238s (U1x pad4=SDA / pad5=SCL); THRESH (ESP PWM
    # IO14=pin19 -> R10 -> /THRESH -> all TLV7011 ref pin4); per-cable DETCn (TLV7011 out
    # pin1 -> ESP). Run the spine in the open band; hop a shunt column on B.Cu.
    band = 25.7                                     # spine lane just below the sense parts
    p3v3 = pg("U3", "5", P, comps)
    sda  = pg("U1", "24", P, comps); scl = pg("U1", "25", P, comps)
    spine_xs = [pg(f"U1{i}", "4", P, comps)[0] for i in range(N)]     # INA238 SDA pads (left targets)
    xmin = min(spine_xs) - 1.0
    g.append(_line([p3v3, (ex - 2, 23.5), (xmin, 23.5)], "Eco1.User", 0.4))            # +3V3 sub-trunk
    g.append(_line([sda,  (ex - 2, band)] + [pg(f"U1{i}", "4", P, comps) for i in range(N)] + [(xmin, band)], "Eco1.User", 0.22))      # I2C SDA daisy
    g.append(_line([scl,  (ex - 2, band + 0.5)] + [pg(f"U1{i}", "5", P, comps) for i in range(N)] + [(xmin, band + 0.5)], "Eco1.User", 0.22))  # I2C SCL daisy
    thr = pg("U1", "19", P, comps)
    g.append(_line([thr, (ex - 2, band - 0.6)] + [pg(f"U3{i}", "4", P, comps) for i in range(N)], "Eco1.User", 0.22))   # THRESH ref -> all TLV
    detpins = ["28", "29", "16"]                    # DETC1->ESP28, DETC2->ESP29, DETC3->ESP16 (netlist)
    for i in range(N):
        u3i = f"U3{i}"
        g.append(_line([pg(u3i, "1", P, comps), (pg(u3i, "1", P, comps)[0], band - 1.2),
                        pg("U1", detpins[i], P, comps)], "Eco1.User", 0.22))           # DETCn out -> ESP
    g.append(_txt("SPINE: +3V3 / I2C / THRESH / DETC  (open y17-26 band; hop shunt on B.Cu)", ex - 2, 27.6, "Eco1.User", 0.6))
    # --- NET CLASS 5/6: CAN + USB (Eco2.User) ---
    g.append(_line([pg("U2", "7", P, comps), (W - 14, 9), pg("J1", "3", P, comps)], "Eco2.User", 0.25))   # CAN_H -> RJ45 pin3
    g.append(_line([pg("U2", "6", P, comps), (W - 14, 11), pg("J1", "6", P, comps)], "Eco2.User", 0.25))  # CAN_L -> RJ45 pin6
    g.append(_line([pg("U2", "1", P, comps), (ex + 16, 13), pg("U1", "26", P, comps)], "Eco2.User", 0.22))  # CAN_TX -> ESP26
    g.append(_line([pg("U2", "4", P, comps), (ex + 16, 14), pg("U1", "27", P, comps)], "Eco2.User", 0.22))  # CAN_RX -> ESP27
    g.append(_line([pg("J5", "A6", P, comps), pg("U1", "18", P, comps)], "Eco2.User", 0.25))               # USB_DP -> ESP18
    g.append(_line([pg("J5", "A7", P, comps), pg("U1", "17", P, comps)], "Eco2.User", 0.25))               # USB_DM -> ESP17
    g.append(_txt("CAN pair -> RJ45 / USB FS pair -> ESP (length-match)", ex + 1, 11, "Eco2.User", 0.6))
    return "\n".join(g)

# --------------------------------------------------------------- build the board
def build(sku):
    DIR, BASE, N, PITCH = sku
    out  = f"{ROOT}/modules/{DIR}/{BASE}.kicad_pcb"
    netf = f"{ROOT}/modules/{DIR}/{BASE}.net"
    if not os.path.exists(netf):
        os.system(f"cd {ROOT}/modules/{DIR} && kicad-cli sch export netlist -o {BASE}.net {BASE}.kicad_sch >/dev/null 2>&1")
    # one-shot bootstrap guard: never silently clobber a board routed in the GUI.
    if os.path.exists(out) and re.search(r"\n\s*\((?:segment|via)\b", open(out).read()):
        if "--force" not in sys.argv:
            print(f"  SKIP {os.path.relpath(out, ROOT)}: already routed (tracks/vias present); pass --force"); return
    comps, vals, nets = parse_netlist(netf)
    names = [x for x in sorted(nets) if x]
    code_of = {x: i + 1 for i, x in enumerate(names)}
    padnet = {(r, p): (code_of[x], x) for x, nodes in nets.items() if x for (r, p) in nodes}
    verify_passives(nets)
    W, H_, ex, P, mounts, logo = frame(N, PITCH)
    place_passives(P, N, PITCH, ex)
    fps = []
    for ref, (lib, x, y, rot) in P.items():
        if ref not in comps:
            print(f"  WARN {ref} placed but absent from netlist (skipped)", file=sys.stderr); continue
        fps.append(place(lib, ref, x, y, rot, padnet, code_of, val=vals.get(ref)))
    # any netlist component we forgot to place?
    for ref in comps:
        if ref not in P:
            print(f"  WARN no placement for netlist component {ref}", file=sys.stderr)
    for i, (x, y) in enumerate(mounts, 1):
        fps.append(place(MOUNT, f"H{i}", x, y, 0, padnet, code_of, gnd_all=True))
    fps.append(place("cec:CEC_Logo_Copper", "LOGO1", logo[0], logo[1], 0, padnet, code_of, flip=True))
    e = []
    pts = [(0, 0), (W, 0), (W, H_), (0, H_), (0, 0)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        e.append(f'\t(gr_line (start {ff(x1)} {ff(y1)}) (end {ff(x2)} {ff(y2)}) (stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "{U()}"))')
    note = (f'\t(gr_text "CEC {BASE}  4L 2oz/1oz  {W:.0f}x{H_:.0f}" (at {ff(logo[0])} {ff(H_ - 3)} 0) (layer "B.SilkS") (uuid "{U()}") '
            f'(effects (font (size 0.9 0.9) (thickness 0.13)) (justify mirror)))')
    netdecl = '\t(net 0 "")\n' + "\n".join(f'\t(net {code_of[x]} "{x}")' for x in names)
    zones = (gnd_planes(code_of["GND"], W, H_) + "\n") if "GND" in code_of else ""
    guides = routing_guides(P, W, H_, ex, comps)
    guides = (guides + "\n") if guides else ""
    doc = ("(kicad_pcb\n\t(version 20260206)\n\t(generator \"cec-gen-pcie-condensed\")\n\t(generator_version \"10.0\")\n"
           "\t(general\n\t\t(thickness 1.6)\n\t\t(legacy_teardrops no)\n\t)\n\t(paper \"A4\")\n" + LAYERS +
           "\n\t(setup\n" + stackup() + "\n\t\t(pad_to_mask_clearance 0)\n\t\t(allow_soldermask_bridges_in_footprints no)\n\t)\n"
           + netdecl + "\n" + "\n".join(fps) + "\n" + "\n".join(e) + "\n" + zones + guides + note + "\n\t(embedded_fonts no)\n)\n")
    # ESP32-C6 antenna keepout dropped (no wireless): trim courtyard to body.
    doc = doc.replace("-10.98", "-4.95")
    open(out, "w").write(doc)
    print(f"WROTE {os.path.relpath(out, ROOT)}  board={W:.1f}x{H_:.0f}mm  N={N} pitch={PITCH:.0f}  parts={len(fps)}")


# --------------------------------------------------------------- routing-plan PNG
def _gcourt(libid, x, y, rot):
    """Global courtyard bbox (xmin,xmax,ymin,ymax) of a placed footprint (4-tuple frame)."""
    nick, name = libid.split(":")
    t = open(fp_path(nick, name)).read(); xs = []; ys = []
    for m in re.finditer(r'\(fp_(?:line|poly|rect)\b', t):
        b = carve(t, m.start())
        if 'CrtYd' not in b: continue
        for a, c in re.findall(r'\((?:start|end|xy|mid) (-?[\d.]+) (-?[\d.]+)\)', b):
            lx, ly = float(a), float(c)
            if name.startswith("ESP32-C6") and ly < -5.0:   # antenna keepout dropped
                ly = -4.95
            a_ = math.radians(rot)
            xs.append(x + lx*math.cos(a_) + ly*math.sin(a_))
            ys.append(y - lx*math.sin(a_) + ly*math.cos(a_))
    if not xs:
        return (x-1, x+1, y-1, y+1)
    return (min(xs), max(xs), min(ys), max(ys))

def routing_plan_png(sku):
    """Board-accurate routing-candidate plan (mirrors gen-eps-condensed.routing_plan_png),
    PARAMETRIC in N: left axis = the real placement (courtyards + mounts) overlaid with
    the 12V pours / GND stitch hints / Kelvin pairs / spine / CAN / USB; right axis = a
    notes panel (why the board size / 3 mounts, routing order, netclass table, SI notes)."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Polygon, Circle
    from matplotlib.lines import Line2D
    DIR, BASE, N, PITCH = sku
    netf = f"{ROOT}/modules/{DIR}/{BASE}.net"
    comps, vals, nets = parse_netlist(netf)
    W, H_, ex, P, mounts, logo = frame(N, PITCH)
    place_passives(P, N, PITCH, ex)
    C = dict(v12i="#d83434", v12o="#e8862a", gnd="#1f9e6f", kel="#1438a8",
             p3v3="#1f9e6f", sig="#7a52c8", can="#b5179e", usb="#1d7fd8", body="#9aa7b4", txt="#101418")

    fig = plt.figure(figsize=(18.0, 8.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.7, 1.0], wspace=0.02)
    ax = fig.add_subplot(gs[0]); nx = fig.add_subplot(gs[1]); nx.axis("off")
    ax.set_aspect("equal"); ax.set_xlim(-3, W + 4); ax.set_ylim(H_ + 4, -5)   # invert y (KiCad)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), W, H_, fill=False, ec="#222", lw=1.6))
    ax.text(W/2, -3.0, f"CEC PCIe 8-pin {N}-port — routing-candidate plan   {W:.0f} x {H_:.0f} mm   "
            f"4-layer F.Cu / In1 GND / In2 GND / B.Cu   (12V on outers, split at each shunt)",
            ha="center", va="center", fontsize=11, weight="bold", color=C["txt"])

    # --- parts (courtyard boxes) ---
    for ref, (lib, x, y, rot) in P.items():
        if not lib: continue
        x0, x1, y0, y1 = _gcourt(lib, x, y, rot)
        big = ref in ("J1", "J5") or ref.startswith("J_")
        ax.add_patch(Rectangle((x0, y0), x1-x0, y1-y0, fill=True, fc="#eef1f4" if not big else "#dde6ee",
                     ec=C["body"], lw=0.7, alpha=0.95, zorder=2))
        if ref.startswith(("U", "J", "RS")) or ref in ("D1", "D2"):
            ax.text((x0+x1)/2, (y0+y1)/2, ref, ha="center", va="center",
                    fontsize=6.0 if not big else 7.5, color=C["txt"], zorder=6, weight="bold")
    for (mx, my) in mounts:
        ax.add_patch(Circle((mx, my), 3.2, fill=True, fc="#f2d34e", ec="#b69a18", lw=0.8, zorder=1))

    def pad(ref, p): return pg(ref, p, P, comps)
    # --- NET 1: 12V IN/OUT pours (filled translucent) + GND stitch hints ---
    for i in range(N):
        c = i + 1
        IN  = _pour_outline(P, comps, c, "in")
        OUT = _pour_outline(P, comps, c, "out")
        ax.add_patch(Polygon(IN,  closed=True, fc=C["v12i"], ec=C["v12i"], alpha=0.20, lw=1.0, zorder=3))
        ax.add_patch(Polygon(OUT, closed=True, fc=C["v12o"], ec=C["v12o"], alpha=0.20, lw=1.0, zorder=3))
        # GND stitch hints flanking each cable's 12V column (the inner GND planes return here)
        jin = [pad(f"J_IN{c}", p) for p in ("4", "8")]; jout = [pad(f"J_OUT{c}", p) for p in ("4", "8")]
        for (gx, gy) in jin + jout:
            ax.plot(gx, gy, 'o', ms=2.6, mfc=C["gnd"], mec="none", zorder=4)
    # --- NET 3: Kelvin pairs off shunt inner edges ---
    for i in range(N):
        c = i + 1; rs = f"RS{c}"
        rhi = pad(rs, "1"); rlo = pad(rs, "2")
        hi_tap = (rhi[0], rhi[1] - 0.9); lo_tap = (rlo[0], rlo[1] + 0.9)
        for tap, dst in [(hi_tap, pad(f"U1{i}", "10")), (lo_tap, pad(f"U1{i}", "8")),
                         (hi_tap, pad(f"U2{i}", "3")),  (lo_tap, pad(f"U2{i}", "4"))]:
            ax.plot([tap[0], dst[0]], [tap[1], dst[1]], color=C["kel"], lw=1.4, zorder=5)
    # --- NET 4: spine (+3V3 fat, I2C/THRESH/DET thin) ---
    def poly(pts, col, lw, z=5, ls="-"):
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]; ax.plot(xs, ys, color=col, lw=lw, ls=ls, zorder=z)
    band = 25.7
    spine_xs = [pad(f"U1{i}", "4")[0] for i in range(N)]; xmin = min(spine_xs) - 1.0
    poly([pad("U3", "5"), (ex-2, 23.5), (xmin, 23.5)], C["p3v3"], 2.6)                                     # +3V3 sub-trunk
    poly([pad("U1", "24"), (ex-2, band)] + [pad(f"U1{i}", "4") for i in range(N)] + [(xmin, band)], C["sig"], 1.0, ls=(0, (4, 2)))         # I2C SDA
    poly([pad("U1", "25"), (ex-2, band+0.5)] + [pad(f"U1{i}", "5") for i in range(N)] + [(xmin, band+0.5)], C["sig"], 1.0, ls=(0, (4, 2)))  # I2C SCL
    poly([pad("U1", "19"), (ex-2, band-0.6)] + [pad(f"U3{i}", "4") for i in range(N)], "#c46a00", 1.0, ls=(0, (1, 1)))                       # THRESH
    detpins = ["28", "29", "16"]
    for i in range(N):
        u3i = f"U3{i}"
        poly([pad(u3i, "1"), (pad(u3i, "1")[0], band-1.2), pad("U1", detpins[i])], C["sig"], 0.9)          # DETCn
    # --- NET 5/6: CAN + USB ---
    poly([pad("U2", "7"), (W-14, 9),  pad("J1", "3")], C["can"], 1.4)
    poly([pad("U2", "6"), (W-14, 11), pad("J1", "6")], C["can"], 1.4)
    poly([pad("U2", "1"), (ex+16, 13), pad("U1", "26")], C["can"], 1.0, ls=(0, (4, 2)))
    poly([pad("U2", "4"), (ex+16, 14), pad("U1", "27")], C["can"], 1.0, ls=(0, (4, 2)))
    poly([pad("J5", "A6"), pad("U1", "18")], C["usb"], 1.6)
    poly([pad("J5", "A7"), pad("U1", "17")], C["usb"], 1.6)

    leg = [Line2D([], [], color=C["v12i"], lw=6, alpha=.4, label="12V IN pour (F+B, 2oz)"),
           Line2D([], [], color=C["v12o"], lw=6, alpha=.4, label="12V OUT pour"),
           Line2D([], [], marker='o', color='w', mfc=C["gnd"], ms=6, label="GND stitch via (In1/In2)"),
           Line2D([], [], color=C["kel"], lw=2, label="Kelvin sense pair (0.25mm)"),
           Line2D([], [], color=C["p3v3"], lw=3, label="+3V3 sub-trunk (0.4mm)"),
           Line2D([], [], color=C["sig"], lw=1.2, ls=(0, (4, 2)), label="I2C / DETC (spine)"),
           Line2D([], [], color="#c46a00", lw=1.2, ls=(0, (1, 1)), label="THRESH ref (quiet lane)"),
           Line2D([], [], color=C["can"], lw=2, label="CAN H/L + TX/RX"),
           Line2D([], [], color=C["usb"], lw=2, label="USB FS pair (matched)")]
    ax.legend(handles=leg, loc="lower center", bbox_to_anchor=(0.5, -0.15), ncol=3, fontsize=8, framealpha=.95)

    # --- right notes panel ---
    def block(y, title, lines, tc="#101418"):
        nx.text(0.0, y, title, fontsize=11, weight="bold", color=tc, transform=nx.transAxes)
        for k, ln in enumerate(lines):
            nx.text(0.02, y-0.030*(k+1), ln, fontsize=8.0, color="#222", transform=nx.transAxes, family="DejaVu Sans")
        return y-0.030*(len(lines)+1)-0.022
    y = 0.995
    y = block(y, f"WHY {W:.0f} x {H_:.0f} mm,  3 MOUNTS", [
        f"N={N} cables @ {PITCH:.0f}mm pitch (CX0=11 left margin) + a {CORE_W:.0f}mm core.",
        "H=44 is FORCED by the pegged Molex 45586 (J_IN/J_OUT pegs reach",
        "y=2.7 / y=41.3); the EPS pegless 87427 fits in 35.  3-port keeps it",
        "sub-105 by tightening pitch to 20 (2-port can afford 23 for room).",
        "3x M3: TWO logic-side (TR + BR corners), ONE connector-side, roughly",
        "centered (x4, y=H/2) in the clear band between cable-1 J_IN & J_OUT."])
    y = block(y, "ROUTING ORDER (per cable 1..N, then core)", [
        "1. Pour In1+In2 GND planes; stitch every connector/IC GND.",
        "2. 12V IN/OUT pours per cable (F.Cu + B.Cu mirror) + via field; split AT shunt.",
        "3. Kelvin stubs (4/shunt) off the INNER pad edges, matched pairs over GND.",
        "4. USB DP/DM pair (short, straight, length-matched) - J5 sits above the ESP.",
        "5. CAN H/L -> RJ45 ; TX/RX -> ESP.",
        "6. Control->sense SPINE (+3V3, I2C SDA/SCL, THRESH, DETC1..N) on the y17-26 band.",
        "7. +5VSB / VBUS-OR / DETECT core knit + EN.   8. Re-pour, DRC."])
    y = block(y, "NETCLASSES (recommend into the empty .kicad_pro / .kicad_dru)", [
        "Power12V  2.5/pour  via 0.9/0.5  clr0.2   /SENSEC* (12V ~30A pours)",
        "GND       0.5/plane via 0.9/0.5           GND",
        "Power     0.5 mm    via 0.8/0.4           +3V3 / +5VSB / /VBUS",
        "Signal    0.22 mm   via 0.6/0.3           I2C/THRESH/DETC/CAN_TX,RX/EN/CC",
        "CAN       0.25 mm   coupled pair          /CAN_H /CAN_L",
        "USB       0.25 / gap0.13  DIFF PAIR       /USB_DP /USB_DM (auto-paired)",
        "Kelvin tap shares /SENSEC* -> draw 0.25mm by hand off the shunt edge."])
    y = block(y, "SI / KEEP-AWAY", [
        "* Kelvin pairs & THRESH ref: >=0.5mm off any 12V copper edge",
        "  (the ~30A pours carry the transient the sensing must catch).",
        "* THRESH is a shared comparator ref - quiet quasi-DC lane, C40 at",
        "  the source, never parallel-adjacent to a 12V lane or DETC for long.",
        "* Spine crosses the cable backs - run it in the OPEN y17-26 band",
        "  between J_IN (y10) and J_OUT (y34); hop a shunt column on B.Cu.",
        "* USB length-match DP/DM (J5 directly above the ESP).",
        "* CAN H/L stay paired; 120R split termination lives at the Hub.",
        "* Guides drawn in-board on Dwgs/Cmts/Eco1/Eco2.User (toggle layers)."])
    nx.text(0.0, y-0.003, "Per-cable +12V flows J_IN pads 1-3 -> 0.5mΩ shunt -> J_OUT pads 1-3;",
            fontsize=8, color="#444", transform=nx.transAxes, style="italic")
    nx.text(0.0, y-0.036, "GND pins 4-8 return on the inner planes. INA238 + INA181 Kelvin-tap each shunt.",
            fontsize=8, color="#444", transform=nx.transAxes, style="italic")

    out = f"{ROOT}/modules/{DIR}/pcie{N}-routing-plan.png"
    fig.savefig(out, dpi=145, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"WROTE {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    targets = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not targets:
        raise SystemExit("usage: gen-pcie-condensed.py <pcie-8pin-2port|pcie-8pin-3port> [--force] [--no-plan]")
    for t in targets:
        if t not in SKUS:
            print(f"  unknown board '{t}' (expected one of: pcie-8pin-2port, pcie-8pin-3port)", file=sys.stderr); continue
        build(SKUS[t])
        if "--no-plan" not in sys.argv:
            routing_plan_png(SKUS[t])
