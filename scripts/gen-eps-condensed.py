#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# EPS 8-pin condensed floorplan -- the WORKED EXAMPLE of the repo-wide layout toolkit
# scripts/cec_pcb.py. This driver only supplies EPS-specific DATA; every ability
# (passive clustering, routing-candidate guides, the routing-plan PNG, netclasses, the
# .kicad_dru, and the board build) comes from cec_pcb. Any other board can be driven the
# same way -- see scripts/README-cec_pcb.md.
#
#   python3 scripts/gen-eps-condensed.py            # board + guides + plan + netclasses + DRU
#   python3 scripts/gen-eps-condensed.py --no-plan  # skip the PNG
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_pcb as cp

DIR, BASE, N = "eps-8pin", "eps8pin-module", 2
ROOT = cp.ROOT
# H 35 -> 37: push J_OUT down ~2mm so the cross-board spine gets a ~5mm clear channel
# (sense parts bottom out ~y21.7, J_OUT now starts ~y26.5 -> y22-26 open). Connectors
# overhang their edge, so a 2mm-taller board is cheap.
CX0, PITCH, H = 11.0, 23.0, 37.0     # 11mm left margin (clears a left M3), 23mm cable pitch

# ----------------------------------------------------------------- frame (anchors)
def frame():
    cables_right = CX0 + (N - 1) * PITCH + 16.2
    ex = cables_right + 3.8
    W = round(ex + 42.0)
    P = {}
    for i in range(N):
        Xc, c = CX0 + i * PITCH, i + 1
        # pegless 87427: J_IN rot180 (mouth->top, GND row y4 / +12V row y9.5), J_OUT rot0
        # (mouth->bottom). J_OUT at Xc+12.6 keeps the +12V columns aligned (straight shunt).
        P[f"J_IN{c}"]  = (Xc, 4.0, 180)
        P[f"J_OUT{c}"] = (Xc + 12.6, H - 4.0, 0)      # H 37 -> J_OUT down ~2mm (wider spine channel)
        # shunt rot 90 -> 270 so pad1 (=/SENSEC*_HI, J_IN/top side) is the UPPER terminal,
        # matching top->bottom current flow; the INA238 Kelvin taps no longer cross. (At rot90
        # HI sat BELOW LO -> the inversion this fixes.)
        P[f"RS{c}"]    = (Xc + 6.8, 17.5, 270)        # 0.5mOhm shunt, vertical in the 12V column
        P[f"U1{i}"]    = (Xc + 0.5, 17.5, 0)          # INA238 (U10/U11), left of shunt
        # INA181 rot 0 -> 180 so its HI/LO sense pads (3/4) face the shunt (was: +3V3/GND pads
        # 5/6 stacked over the LO escape, blocking it).
        P[f"U2{i}"]    = (Xc + 11.8, 15.0, 180)       # INA181A2 (U20/U21), right of shunt
        P[f"U3{i}"]    = (Xc + 11.8, 20.0, 0)         # TLV7011 (U30/U31)
    P.update({
        "J5": (ex + 8.0, 4.0, 180), "U1": (ex + 9.0, 22.0, 180), "U3": (ex + 20.0, 14.0, 0),
        # U2 (CAN xcvr) moved from the far-right (ex+29) to the J5-bottom / ESP-top band so
        # its CAN_TX/RX (pins 1/4, left) short-hop to the ESP's CAN pads 26/27 on the ESP left
        # edge; CAN_H/L (pins 6/7, right) run to J1 on the right edge.
        "U2": (ex + 6.0, 12.0, 0), "SW1": (ex + 19.0, 27.0, 0), "SW2": (ex + 25.0, 27.0, 0),
        "D2": (ex + 20.0, 4.0, 90), "J1": (ex + 38.0, 18.0, 90),
    })
    mounts = [(4.0, 4.5), (4.0, H - 4.5), (W - 4.0, H - 4.0)]
    # logo moved OFF the ESP underside (was ex+9,20 = under the ESP, the sole B.Cu blocker for
    # signals escaping to the ESP) to a dead back-side area RIGHT of the ESP, below the SW
    # buttons -- clear of the ESP underside, the spine, and all THT pads (only overlaps the
    # SMD button courtyards, a different copper layer).
    return W, H, ex, P, mounts, (W - 19.0, 26.0)

# Passive engine inputs (netlist-verified): GEOM = where each decoupler sits (owner +
# power pad, fed to cp.auto_cluster); OWN = the net it must share (fed to verify).
GEOM = {
    "C3": ("U1","3"), "C7": ("U1","3"), "C5": ("U1","8"), "R2": ("U1","8"),
    "R10": ("U1","19"), "C40": ("U1","19"), "R3": ("U1","24"), "R4": ("U1","25"),
    "C4": ("U2","3"), "C8": ("U2","5"), "C1": ("U3","1"), "C2": ("U3","5"), "C6": ("U3","1"),
    "C9": ("J5","A4"), "R8": ("J5","A5"), "R9": ("J5","B5"),
    "C10": ("U10","6"), "C11": ("U11","6"), "C20": ("U20","6"), "C21": ("U21","6"),
    "C30": ("U30","5"), "C31": ("U31","5"), "D1": ("J1","8"), "R1": ("J1","8"), "R7": ("J1","8"),
}
OWN = {
    "C3": ("U1","+3V3","ESP +3V3 HF bypass"), "C7": ("U1","+3V3","ESP +3V3 bulk"),
    "C5": ("U1","/EN","ESP EN RC"), "R2": ("U1","/EN","ESP EN pull-up"),
    "R10": ("U1","/THRESH_PWM","THRESH series R"), "C40": ("U30","/THRESH","THRESH filter (shared)"),
    "R3": ("U1","/I2C_SDA","I2C SDA pull-up"), "R4": ("U1","/I2C_SCL","I2C SCL pull-up"),
    "C4": ("U2","+5VSB","CAN VCC bypass"), "C8": ("U2","+3V3","CAN VIO bypass"),
    "C1": ("U3","+5VSB","LDO VIN"), "C2": ("U3","+3V3","LDO VOUT"), "C6": ("U3","+5VSB","+5VSB entry bulk"),
    "C9": ("J5","/VBUS","USB VBUS bulk"), "R8": ("J5","/USB_CC1","CC1 pull-down"), "R9": ("J5","/USB_CC2","CC2 pull-down"),
    "C10": ("U10","+3V3","INA238 C1 bypass"), "C11": ("U11","+3V3","INA238 C2 bypass"),
    "C20": ("U20","+3V3","INA181 C1 bypass"), "C21": ("U21","+3V3","INA181 C2 bypass"),
    "C30": ("U30","+3V3","TLV C1 bypass"), "C31": ("U31","+3V3","TLV C2 bypass"),
    "D1": ("J1","/DETECT","DETECT ESD"), "R1": ("J1","/DETECT","DETECT code"), "R7": ("J1","/DETECT","DETECT poke"),
}

def offsets(ex):
    """Hand-refined DRC-clean passive positions (frame-relative) -- the DEFAULT placement.
    Pass --auto to instead drive cp.auto_cluster from GEOM (the generic geometry placer,
    which gives a structurally-clean starting placement to refine in the GUI)."""
    t = {}
    for i in range(N):
        Xc = CX0 + i * PITCH
        t[f"C1{i}"] = (Xc + 0.5, 14.0, 0)    # C10/C11 INA238 VS bypass
        t[f"C2{i}"] = (Xc + 16.7, 15.0, 0)   # C20/C21 INA181 VS bypass (out +1.5mm; INA181 rot180
                                             #   moved its sense pads, keep the LO escape clear)
        t[f"C3{i}"] = (Xc + 15.2, 20.0, 0)   # C30/C31 TLV7011 VCC bypass
    t.update({
        # C6 (+5VSB entry bulk) and C3 (ESP +3V3 HF) relocated off U2's new band: C6 -> by the
        # LDO VIN (71,10), C3 -> the +3V3 cluster (70,15). (Their old ex+2.5/ex+6.0,13.5 spots
        # are now under U2 at (60,12).)
        "C6": (71.0,10.0,0), "C3": (70.0,15.0,0), "C7": (ex+13.0,13.5,0),         # +5VSB / ESP +3V3
        "C1": (ex+17.5,16.5,0), "C2": (ex+22.5,16.5,0),                           # LDO in/out
        "C5": (ex+25.0,13.5,0), "R2": (ex+27.0,13.5,0),                           # ESP EN RC
        "R3": (ex+18.0,20.0,0), "R4": (ex+20.0,20.0,0),                           # I2C pull-ups
        "R10": (ex+25.0,18.0,0), "C40": (ex+27.0,18.0,0),                         # THRESH RC
        "R8": (ex+15.0,4.0,0), "R9": (ex+17.0,4.0,0), "C9": (ex+12.0,10.5,0),     # USB CC / VBUS
        "C4": (ex+26.5,8.0,0), "C8": (ex+31.5,8.0,0),                             # CAN bypass
        "D1": (ex+30.0,26.0,0), "R1": (ex+33.0,26.0,0), "R7": (ex+35.5,26.0,0),   # DETECT front-end
    })
    return t

# ----------------------------------------------------------------- routing candidates
COL = dict(v12i="#d83434", v12o="#e8862a", kel="#1438a8", p3v3="#1f9e6f",
           sig="#7a52c8", thr="#c46a00", can="#b5179e", usb="#1d7fd8")

def route_data(P, comps):
    """EPS routes as both guide-graphics (for the board) and plan-geometry (for the PNG)."""
    pad = lambda r, p: cp.pad_global(r, p, P, comps)
    guides, pours, traces, vias = [], [], [], []
    # +12V IN/OUT pours per cable (split at the shunt)
    for i in range(N):
        dx = i * PITCH
        IN  = [(9.5+dx,8),(25.1+dx,8),(25.1+dx,13),(20+dx,13),(20+dx,15.6),(15.6+dx,15.6),(15.6+dx,13),(9.5+dx,13)]
        OUT = [(15.6+dx,19.4),(20+dx,19.4),(20+dx,22),(25.1+dx,22),(25.1+dx,27),(9.5+dx,27),(9.5+dx,22),(15.6+dx,22)]
        guides += [{"poly": IN+[IN[0]], "layer": "Dwgs.User"}, {"text": f"12V_IN{i+1}", "at": (10+dx,6.6), "layer":"Dwgs.User"},
                   {"poly": OUT+[OUT[0]], "layer": "Dwgs.User"}, {"text": f"12V_OUT{i+1}", "at": (10+dx,28.4), "layer":"Dwgs.User"}]
        pours += [(IN, COL["v12i"], 0.22, f"12V_IN{i+1}", (10+dx,6.6)), (OUT, COL["v12o"], 0.22, None, None)]
        for gy in (5.5,6.8,28.2,29.5):
            for gx in (10.2+dx,24.4+dx): vias.append((gx,gy))
    # Kelvin pairs off each shunt's inner edge
    for i in range(N):
        rsx = (CX0+i*PITCH)+6.8
        for tap, dst in [((rsx,15.9),pad(f"U1{i}","10")),((rsx,19.1),pad(f"U1{i}","8")),
                         ((rsx,15.9),pad(f"U2{i}","3")),((rsx,19.1),pad(f"U2{i}","4"))]:
            guides.append({"line":[tap,dst],"layer":"Cmts.User","w":0.25}); traces.append(([tap,dst],COL["kel"],1.4,"-"))
    guides.append({"text":"Kelvin: tap shunt INNER edge, matched pair over In1 GND","at":(11,13.2),"layer":"Cmts.User","size":0.6})
    # control->sense SPINE -- re-spec'd off the false "y17 lane" (occupied by the ESP body
    # y16.4-28, the LDO, and the INA238 pad rows y15.8-19.2). It now runs the WIDENED
    # y22-25 channel (sense parts bottom ~y21.7; J_OUT pushed to y26.1). 6 nets split by layer:
    #   F.Cu, in-channel: I2C SDA/SCL  (hop the shunt body on B.Cu where they cross a 12V column)
    #   B.Cu (quasi-DC): THRESH (shared comparator ref) + DETC1/DETC2 -- B.Cu under the ESP is
    #     now FREE (logo moved), so DETC1/2 dive to B.Cu right at the ESP and hop each shunt col.
    YF, YB = 23.2, 24.4      # F.Cu I2C lane / B.Cu THRESH+DETC lane in the channel
    spine = [
        # +3V3 sub-trunk: LDO -> sense ICs, along the F.Cu channel top
        ([pad("U3","5"),(70,22.6),(45,22.6),(22,22.6),(9.5,22.6),(9.3,19.0)], COL["p3v3"],2.6,"-"),
        # I2C SDA/SCL on F.Cu in the channel (ESP left edge -> U11 -> U10)
        ([pad("U1","24"),(54,YF),(32.3,YF),(32.3,18.4),(9.5,YF),(9.3,18.4)], COL["sig"],1.0,(0,(4,2))),
        ([pad("U1","25"),(53,YF+0.5),(32.3,YF+0.5),(9.5,YF+0.5),(9.3,18.9)], COL["sig"],1.0,(0,(4,2))),
        # THRESH (shared ref): R10 near ESP -> TLV U31.4 / U30.4, on B.Cu
        ([pad("R10","2"),(60,YB),(45,YB),(44.66,18.7),(22,YB),(21.66,18.7)], COL["thr"],1.0,(0,(1,1))),
        # THRESH_PWM stub: ESP IO19 -> R10 (short)
        ([pad("U1","19"),(70,YB-0.6),pad("R10","1")], COL["thr"],0.9,(0,(1,1))),
        # DETC1/DETC2: ESP -> B.Cu (under ESP now free) -> TLV outputs, hop each shunt col on B.Cu
        ([pad("U1","28"),(54,YB+0.6),(40,YB+0.6),(21.66,YB+0.6),pad("U30","1")], COL["sig"],0.9,(0,(2,2))),
        ([pad("U1","29"),(54,YB+1.2),(44.66,YB+1.2),pad("U31","1")], COL["sig"],0.9,(0,(2,2))),
    ]
    for pts,c,w,ls in spine:
        guides.append({"line":pts,"layer":"Eco1.User","w":0.22}); traces.append((pts,c,w,ls))
    guides.append({"text":"SPINE y22-25: I2C SDA/SCL F.Cu | THRESH+DETC1/2 B.Cu (under ESP free) | hop shunt cols on B.Cu","at":(28,25.6),"layer":"Eco1.User","size":0.55})
    # CAN + USB
    # CAN_H/L (U2 now in the J5-bottom / ESP-top band, pins 6/7 on its right) run UP+OVER and
    # down the FAR-RIGHT board edge (x>=93) to enter J1 from the right -- this DODGES the DETECT
    # pin J1.8 (89.5,9.1) and the D1/R1/R7 DETECT cluster (~x84-89, y26) rather than crossing them.
    # CAN_TX/RX (U2 pins 1/4 on its left) short-hop straight DOWN the ESP left edge to IO20/IO21.
    can = [([pad("U2","7"),(64,11),(94,11),(94,15.46),pad("J1","3")], COL["can"],1.4,"-"),    # CAN_H far-right edge
           ([pad("U2","6"),(64,12.6),(93.2,12.6),(93.2,11.65),pad("J1","6")], COL["can"],1.4,"-"),  # CAN_L far-right edge
           ([pad("U2","1"),(57.3,11),(57.1,18.77)], COL["can"],1.0,(0,(4,2))),                 # CAN_TX -> ESP IO20
           ([pad("U2","4"),(57.3,15),(57.1,19.58)], COL["can"],1.0,(0,(4,2)))]                 # CAN_RX -> ESP IO21
    # USB FS pair J5 -> ESP. SIDE-SWAP: J5 has D+ to the RIGHT of D-, the ESP has D+ to the LEFT
    # of D- -> the pair crosses, so D- takes one via to swap legs (drawn as a B.Cu hop midspan).
    usb = [([pad("J5","A6"),(62.5,12.5),pad("U1","18")], COL["usb"],1.6,"-"),                  # D+ stays F.Cu
           ([pad("J5","A7"),(61.0,11.0),(64.5,15.0),pad("U1","17")], COL["usb"],1.6,(0,(3,2)))]# D- via-swap leg
    usb_via = (62.8, 13.5)   # the swap via on the D- leg
    vias.append(usb_via)
    for pts,c,w,ls in can+usb:
        guides.append({"line":pts,"layer":"Eco2.User","w":(0.25 if c==COL["usb"] or w>1 else 0.22)}); traces.append((pts,c,w,ls))
    guides.append({"text":"CAN H/L down FAR-RIGHT edge (dodge DETECT J1.8 + D1/R1/R7) | TX/RX short to ESP","at":(64,9),"layer":"Eco2.User","size":0.55})
    guides.append({"text":"USB FS: D+ F.Cu / D- 1 via to side-swap (J5 D+ right, ESP D+ left)","at":(54,15.8),"layer":"Eco2.User","size":0.5})
    return guides, pours, traces, vias

# ----------------------------------------------------------------- netclasses + DRU
def classes():
    return [
        cp.netclass("Default", 0.2, 0.6, 0.3, 2147483647),
        cp.netclass("Power12V", 2.5, 0.9, 0.5, 0, clr=0.2, color="rgb(220, 50, 30)"),
        cp.netclass("GND", 0.5, 0.9, 0.5, 4, color="rgb(60, 130, 90)"),
        cp.netclass("Power", 0.5, 0.8, 0.4, 5, color="rgb(210, 120, 30)"),
        cp.netclass("Signal", 0.22, 0.6, 0.3, 6),
        cp.netclass("CAN", 0.25, 0.6, 0.3, 2, dpw=0.25, dpg=0.25, color="rgb(180, 20, 150)"),
        cp.netclass("USB", 0.25, 0.6, 0.3, 3, dpw=0.2, dpg=0.13, color="rgb(30, 130, 210)"),
    ]
PATTERNS = [("Power12V","/SENSEC*"),("GND","GND"),("Power","+3V3"),("Power","+5VSB"),("Power","/VBUS"),
    ("CAN","/CAN_H"),("CAN","/CAN_L"),("USB","/USB_D_P"),("USB","/USB_D_N"),
    ("Signal","/I2C_SDA"),("Signal","/I2C_SCL"),("Signal","/THRESH"),("Signal","/THRESH_PWM"),
    ("Signal","/DETC*"),("Signal","/DETAMP*"),("Signal","/DETECT"),("Signal","/DETECT_SENSE"),
    ("Signal","/CAN_TX"),("Signal","/CAN_RX"),("Signal","/EN"),("Signal","/GPIO0"),
    ("Signal","/USB_CC1"),("Signal","/USB_CC2")]
DRU = [
    ("Power min width", "track_width (min 0.5mm)", "A.NetClass == 'Power'"),
    "# NO width floor on /SENSEC* (Power12V): ~30A/cable comes from the 2oz F.Cu+B.Cu\n"
    "# POURS (split at each shunt, verified by area per IPC-2152), and the INA238/INA181\n"
    "# four-wire Kelvin taps live ON these same nets as ~0.25mm stubs -- a track floor would\n"
    "# false-flag them. Power12V clearance is 0.2 (not 0.25) because those Kelvin inputs enter\n"
    "# a 0.5mm-pitch VSSOP-10.",
    ("USB diff pair gap", "diff_pair_gap (min 0.1mm) (max 0.2mm)", "A.NetClass == 'USB' && B.NetClass == 'USB'"),
    "# CAN_H/CAN_L keep the standard (asymmetric) names -> NOT a P/N auto-pair; route them as a\n"
    "# tightly-coupled pair by hand. Only termination is the Hub's split 120R, never on the module.",
]

# ----------------------------------------------------------------- build
def main():
    mod = f"{ROOT}/modules/{DIR}"
    netf = cp.export_netlist(DIR, BASE)
    comps, vals, nets = cp.parse_netlist(netf)
    cp.verify_passives(nets, OWN)
    W, H_, ex, P, mounts, logo = frame()
    if "--auto" in sys.argv:                       # demo the generic geometry placer
        ov = cp.auto_cluster(P, comps, GEOM, drop_keepout={"U1"})
        print(f"  auto_cluster: {len(GEOM)} passives placed, residual overlaps={len(ov)}")
    else:                                          # ship the hand-refined positions (default)
        cp.place_offsets(P, offsets(ex))
    guide_routes, pours, traces, vias = route_data(P, comps)
    gstr = cp.guides(guide_routes)
    cp.build_board(f"{mod}/{BASE}.kicad_pcb", netf, P, mounts, logo, W, H_,
                   guides_str=gstr, drop_keepout={"U1"})
    cp.write_netclasses(f"{mod}/{BASE}.kicad_pro", classes(), PATTERNS)
    cp.write_dru(f"{mod}/{BASE}.kicad_dru", DRU,
                 header="CEC EPS 8-pin module -- custom design rules (auto-loaded by KiCad).\n"
                        "Back the netclasses in eps8pin-module.kicad_pro.")
    if "--no-plan" not in sys.argv:
        leg = [(COL["v12i"],6,"-","12V IN pour (F+B 2oz)"),(COL["v12o"],6,"-","12V OUT pour"),
               ("#1f9e6f",0,"o","GND stitch via"),(COL["kel"],2,"-","Kelvin pair 0.25mm"),
               (COL["p3v3"],3,"-","+3V3 sub-trunk"),(COL["sig"],1.2,(0,(4,2)),"I2C / DET spine"),
               (COL["thr"],1.2,(0,(1,1)),"THRESH ref"),(COL["can"],2,"-","CAN H/L + TX/RX"),
               (COL["usb"],2,"-","USB FS pair")]
        tables = [("ROUTING ORDER", [
            "1. Pour In1+In2 GND planes; stitch every connector/IC GND.",
            "2. 12V IN/OUT pours per cable (F.Cu+B.Cu) + via fields; split at shunt.",
            "3. Kelvin stubs (4/shunt) off the INNER pad edges, matched pairs over GND.",
            "4. §6.13 in-column hops (DETAMPn, short DETn/THRESH stubs).",
            "5. USB DP/DM pair (short; D- 1 via to side-swap legs).  6. CAN H/L -> RJ45 via",
            "   far-right edge (dodge DETECT); TX/RX short down ESP left edge.",
            "7. SPINE in y22-25 channel: I2C SDA/SCL F.Cu | THRESH+DETC1/2 B.Cu (under ESP).",
            "8. +5VSB / VBUS-OR / DETECT core knit + EN.   9. Re-pour, DRC."]),
            ("NETCLASSES (committed: .kicad_pro + .kicad_dru)", [
            "Power12V  2.5/pour via0.9/0.5 clr0.2  /SENSEC* (12V ~30A pours)",
            "GND 0.5/plane via0.9/0.5  ;  Power 0.5 via0.8/0.4  +3V3/+5VSB/VBUS",
            "Signal 0.22 via0.6/0.3  I2C/THRESH/DET/CAN_TX,RX/EN/CC",
            "CAN 0.25 coupled /CAN_H,/CAN_L  ;  USB 0.25 gap0.13 DIFF /USB_D_P,/USB_D_N",
            "Kelvin tap shares /SENSEC* -> draw 0.25mm by hand off the shunt edge."]),
            ("SI / KEEP-AWAY", [
            "* Kelvin pairs & THRESH ref: >=0.5mm off any 12V pour edge.",
            "* THRESH = shared comparator ref; quiet quasi-DC lane, C40 at the source.",
            "* SPINE = the WIDENED y22-25 channel (J_OUT pushed to y26.1, H 35->37):",
            "  I2C SDA/SCL on F.Cu; THRESH+DETC1/2 on B.Cu (ESP underside now free, logo moved);",
            "  hop each shunt 12V column on B.Cu.  Shunt HI-on-top (rot270); INA181 rot180.",
            "* USB length-match DP/DM (J5 above the ESP); D- takes 1 via to side-swap.",
            "* CAN H/L paired down the far-right edge (x>=93); TX/RX on the ESP left edge.",
            "* Guides drawn in-board on Dwgs/Cmts/Eco1/Eco2.User (toggle layers)."])]
        cp.routing_plan_png(f"{mod}/eps-routing-plan.png",
            W=W, H=H_, title=f"CEC EPS 8-pin -- routing-candidate plan   {W:.0f} x {H_:.0f} mm   "
            "4-layer F.Cu / In1 GND / In2 GND / B.Cu  (12V on outers, split at shunt)",
            P=P, comps=comps, pours=pours, traces=traces, vias=vias, tables=tables, legend=leg,
            mounts=[(m[0], m[1], 3.2) for m in mounts], drop_keepout={"U1"},
            subtitle=["Per-cable +12V flows J_IN pads 5-8 -> 0.5mΩ shunt -> J_OUT pads 5-8 (~30A);",
                      "GND pins 1-4 return on the inner planes. INA238 + INA181 Kelvin-tap each shunt."])

if __name__ == "__main__":
    main()
