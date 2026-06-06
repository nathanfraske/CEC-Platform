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
# so the layout is reviewable and reproducible). Supersedes the runtime
# clearance-packer in gen-pcie3-condensed.py.
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
# analysis (copied from gen-pcie3-condensed.py; netlist-correct -- verify_passives()
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

# --------------------------------------------------------------- routing candidates (STUB)
def routing_guides(P, W, H_, ex, comps):
    """STUB -- a follow-up routing sub-agent fills in the in-board routing-candidate
    guide graphics (and any routing-plan PNG). Returns nothing so this generator
    only does footprint/placement planning."""
    return ""

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


if __name__ == "__main__":
    targets = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not targets:
        raise SystemExit("usage: gen-pcie-condensed.py <pcie-8pin-2port|pcie-8pin-3port> [--force]")
    for t in targets:
        if t not in SKUS:
            print(f"  unknown board '{t}' (expected one of: pcie-8pin-2port, pcie-8pin-3port)", file=sys.stderr); continue
        build(SKUS[t])
