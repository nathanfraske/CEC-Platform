#!/usr/bin/env python3
"""Board-accurate route STATUS + PLAN for the 12VHPWR Standard module.

Reads the live .kicad_pcb for real footprint placement and draws a to-scale
top-down plan: what's already routed (high-current J3->shunt on F.Cu, shunt->J4
on B.Cu) vs what remains (per-pin Kelvin sense taps, INA input filters, and the
six INA outputs to the ESP ADC). Lane completion is taken from the DRC
unconnected list at time of writing. Output:
    modules/12vhpwr-standard/12vhpwr-route-plan.png
This is a documentation artifact; the copper itself is laid in the GUI.
"""
import re, math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch, Circle
from matplotlib.lines import Line2D

PCB = "modules/12vhpwr-standard/12vhpwr-standard-module.kicad_pcb"

# ---- parse footprint placements (ref -> x,y,rot) ----
lines = open(PCB).read().splitlines(); N=len(lines)
def grab(i):
    d=0;b=[]
    while i<N:
        b.append(lines[i]); d+=lines[i].count("(")-lines[i].count(")"); i+=1
        if d<=0: break
    return "\n".join(b), i
pos={}
i=0
while i<N:
    if re.match(r'^\t\(footprint ',lines[i]):
        blk,j=grab(i)
        ref=re.search(r'\(property "Reference" "([^"]*)"',blk)
        at=re.search(r'\n\t\t\(at (\S+) (\S+)(?:\s+(\S+))?\)',blk)
        if ref and at: pos[ref.group(1)]=(float(at.group(1)),float(at.group(2)),float(at.group(3) or 0))
        i=j; continue
    i+=1

# board extent
BX0,BX1,BY0,BY1 = 112.875,170.875,58.35,138.35

# lane geometry (from placement)
LANE_X = [116.875+6*k for k in range(6)]      # shunt/INA column centres
J3_12V = [124.66+3*k for k in range(6)]        # J3 +12V pad X (pad1..6), y=62.67
J3_GND = J3_12V                                 # GND row same X, y=65.67
J4_12V = [139.84-3*k for k in range(6)]         # J4 +12V pad X (pad1..6), y=131.83 (reversed)
# J4 +12V_k carries SENSEP(7-k)_LO -> lane index map: padidx j(1..6)->lane (6-j+1)?? from net: pad6->lane1
# J4 pad k (k=1..6) net SENSEP(7-k)_LO. We want, per lane L, the J4 pad feeding it: pad = 7-L.
def j4_pad_x_for_lane(L):   # L=1..6
    k = 7-L
    return 139.84-3*(k-1)
Y_J3_12V, Y_J3_GND, Y_J3_SIG = 62.67,65.67,61.0
Y_J4_12V, Y_J4_GND, Y_J4_SIG = 131.83,128.83,133.5
Y_SH=80.35; Y_FILT=88.35; Y_CF=92.0; Y_INA=97.35

# ---- DRC-derived per-lane sense status (True = DONE) ----
HI_done = {1:False,2:True, 3:True, 4:False,5:False,6:False}   # SENSEPn_HI Kelvin tap -> RFH
LO_done = {1:True, 2:False,3:True, 4:False,5:False,6:False}   # SENSEPn_LO Kelvin tap -> RFL
FILT_done={1:True,2:False,3:True, 4:False,5:False,6:False}    # RFH/RFL -> INA IN+/IN-
ISENSE_done={n:False for n in range(1,7)}                     # INA OUT -> ESP ADC (all remain)

fig=plt.figure(figsize=(15.5,11));
ax=fig.add_axes([0.04,0.05,0.60,0.90])
axn=fig.add_axes([0.66,0.05,0.32,0.90]); axn.axis("off")

# board
ax.add_patch(Rectangle((BX0,BY0),BX1-BX0,BY1-BY0,fill=False,ec="#1b5e20",lw=2))
ax.set_xlim(BX0-4,BX1+4); ax.set_ylim(BY1+4,BY0-4)   # invert Y: board-top at fig-top
ax.set_aspect("equal"); ax.set_title("12VHPWR Standard — route status & plan (board-accurate, 58×80 mm 4-layer)",fontsize=12,fontweight="bold")
ax.set_xlabel("X (mm)"); ax.set_ylabel("Y (mm)")

def pads(xs,y,c,r=0.78,lbl=None):
    for x in xs: ax.add_patch(Circle((x,y),r,fc=c,ec="k",lw=0.4,zorder=5))
# J3 (top)
pads(J3_12V,Y_J3_12V,"#d32f2f"); pads(J3_GND,Y_J3_GND,"#222"); pads([129.16-2*k for k in range(4)],Y_J3_SIG,"#888",r=0.5)
ax.text(132,59.3,"J3  12V-2×6 IN  (rot180)",ha="center",fontsize=9,fontweight="bold")
ax.text(141.5,Y_J3_12V,"+12V",va="center",fontsize=7,color="#d32f2f")
ax.text(141.5,Y_J3_GND,"GND",va="center",fontsize=7)
# J4 (bottom)
pads(J4_12V,Y_J4_12V,"#d32f2f"); pads([139.84-3*k for k in range(6)],Y_J4_GND,"#222")
pads([135.34-2*k for k in range(4)],Y_J4_SIG,"#888",r=0.5)
ax.text(132,137.4,"J4  12V-2×6 OUT pigtail  (rot0)",ha="center",fontsize=9,fontweight="bold")
ax.text(141.5,Y_J4_GND,"GND",va="center",fontsize=7)

# shunts / INA / filter
for n,x in enumerate(LANE_X,1):
    ax.add_patch(Rectangle((x-1.6,Y_SH-1.6),3.2,3.2,fc="#ffd54f",ec="k",lw=0.5,zorder=4))
    ax.text(x,Y_SH,f"RS{n}",ha="center",va="center",fontsize=6)
    ax.add_patch(Rectangle((x-2.0,Y_INA-2.2),4.0,4.4,fc="#90caf9",ec="k",lw=0.5,zorder=4))
    ax.text(x,Y_INA,f"U1{n-1}",ha="center",va="center",fontsize=6)
    ax.add_patch(Rectangle((x-2.4,Y_FILT-0.8),4.8,1.6,fc="#e0e0e0",ec="k",lw=0.3,zorder=3))
ax.text(LANE_X[0]-4.2,Y_SH,"1 mΩ\nshunts",ha="right",va="center",fontsize=7)
ax.text(LANE_X[0]-4.2,Y_FILT,"RFH/RFL\n+CF",ha="right",va="center",fontsize=7)
ax.text(LANE_X[0]-4.2,Y_INA,"INA240\n×6",ha="right",va="center",fontsize=7)

# right-side blocks
def blk(ref,label,w,h,c="#c8e6c9"):
    if ref not in pos: return
    x,y,_=pos[ref]; ax.add_patch(Rectangle((x-w/2,y-h/2),w,h,fc=c,ec="k",lw=0.5,zorder=4)); ax.text(x,y,label,ha="center",va="center",fontsize=6)
blk("U1","ESP32-S3",12,12,"#a5d6a7"); blk("U2","CAN",3,5); blk("U3","LDO",3,3)
blk("J1","RJ45",8,8,"#b0bec5"); blk("J5","USB-C",3,7,"#b0bec5")
for h in ("H1","H2","H3"):
    if h in pos: x,y,_=pos[h]; ax.add_patch(Circle((x,y),1.6,fc="none",ec="#777",lw=1.2)); ax.text(x,y-2.6,h,ha="center",fontsize=6,color="#777")

# ---- DONE high-current routes ----
for n in range(6):
    ax.add_line(Line2D([J3_12V[n],LANE_X[n]],[Y_J3_12V+1,Y_SH-1.6],color="#d32f2f",lw=3,alpha=.85,zorder=2,solid_capstyle="round"))  # J3->shunt F.Cu
    jx=j4_pad_x_for_lane(n+1)
    ax.add_line(Line2D([LANE_X[n],LANE_X[n],jx],[Y_SH+1.6,Y_J4_12V-12,Y_J4_12V-1],color="#f57c00",lw=3,ls=(0,(6,2)),alpha=.85,zorder=2,solid_capstyle="round"))  # shunt->J4 B.Cu

# ---- TODO sense routes ----
def todo(x0,y0,x1,y1):
    ax.add_line(Line2D([x0,x1],[y0,y1],color="#1565c0",lw=1.1,ls=(0,(2,1.5)),zorder=6))
for n in range(1,7):
    x=LANE_X[n-1]
    if not HI_done[n]:  todo(x-0.8,Y_SH-1.6,x-1.6,Y_FILT-0.8)     # shunt HI inner edge -> RFH
    if not LO_done[n]:  todo(x+0.8,Y_SH+1.6,x+1.6,Y_FILT-0.8)     # shunt LO inner edge -> RFL
    if not FILT_done[n]:todo(x-1.6,Y_FILT+0.8,x,Y_INA-2.2); todo(x+1.6,Y_FILT+0.8,x,Y_INA-2.2)
    if not ISENSE_done[n]:                                          # INA OUT -> ESP
        ex,ey,_=pos["U1"]
        ax.add_line(Line2D([x+2,ex-6],[Y_INA, Y_INA-2-(n*0.8)],color="#6a1b9a",lw=1.0,ls=(0,(1,1)),zorder=6))
ax.text(LANE_X[2],Y_INA+4.5,"6× INA OUT → ESP ADC (IO1–6)  — ALL remain",ha="center",fontsize=7,color="#6a1b9a")

# legend
leg=[Line2D([],[],color="#d32f2f",lw=3,label="DONE  J3→shunt  +12V  F.Cu 2.5 mm"),
     Line2D([],[],color="#f57c00",lw=3,ls=(0,(6,2)),label="DONE  shunt→J4  +12V  B.Cu 2.5 mm"),
     Line2D([],[],color="#1565c0",lw=1.1,ls=(0,(2,1.5)),label="TODO  Kelvin taps + RC filter → INA (0.25 mm)"),
     Line2D([],[],color="#6a1b9a",lw=1.0,ls=(0,(1,1)),label="TODO  INA OUT → ESP ADC (0.25 mm)")]
ax.legend(handles=leg,loc="lower left",fontsize=7,framealpha=.95)

# ---------- notes panel ----------
def T(y,s,**k): axn.text(0.0,y,s,va="top",fontsize=k.pop("fs",8.5),transform=axn.transAxes,**k)
y=1.0
T(y,"WHAT'S DONE  ✓",fontweight="bold",fs=11); y-=0.035
T(y,"• All 6 high-current lanes carry +12V end-to-end:\n   J3 +12V → shunt on F.Cu (2.5 mm fan, 3→6 mm),\n   shunt → J4 +12V on B.Cu (2.5 mm).\n• Lane 3 sense chain fully routed (reference lane).\n• Right side: ESP/CAN/LDO/RJ-45/USB-C/flash + sideband\n   taps largely routed.",fs=8); y-=0.135
T(y,"WHAT'S LEFT  (47 ratlines, all sense/signal)",fontweight="bold",fs=11); y-=0.035
T(y,"1) Six INA OUT → ESP ADC IO1–6  (ISENSEP1–6) — ALL.\n2) Kelvin sense taps off the INNER shunt-terminal edges:\n   • HI tap → RFH: lanes 1,4,5,6\n   • LO tap → RFL: lanes 2,4,5,6\n3) RC filter → INA IN+/IN− (INPPn/INNPn): lanes 2,4,5,6.\n   (Lane 1 filter done; lane 3 fully done.)",fs=8); y-=0.135
T(y,"HOW TO ROUTE THE SENSE  (§6.8)",fontweight="bold",fs=11); y-=0.035
T(y,"• 0.25 mm, tight MATCHED-LENGTH pair, run over the\n   In1 GND plane; keep off/⊥ to the 12V lanes.\n• Tap the INNER shunt-pad edges (excludes pad/solder IR);\n   force current enters/leaves the OUTER ends.\n• RC filter (RFH/RFL 10 Ω + CF 470 nF) sits AT the INA pins.\n• Sense vias 0.3/0.6 mm; none on the Kelvin pair itself.\n• The netclasses already auto-apply these widths.",fs=8); y-=0.155
T(y,"+12V ESCAPE (already solved on F.Cu — keep on J4)",fontweight="bold",fs=10.5); y-=0.03
T(y,"+12V is the MIDDLE row; GND barrels (3 mm pitch,\n1.48 mm gaps) sit between +12V and the shunts. Neck each\n+12V to ~0.9 mm THROUGH a GND gap, widen back to 2.5 mm\nbelow. Outer pins (1,6) escape sideways with no neck;\ninner pins (2–5) neck through. Mirror this at J4.",fs=8); y-=0.125
T(y,"BEFORE RE-CHECKING DRC",fontweight="bold",fs=11); y-=0.035
T(y,"• Fill All Zones (B): clears the 252 'actual 0.000 mm'\n   clearance/hole hits — they are STALE GND-pour artifacts\n   (kicad-cli can't refill).  BOTH inner zones = GND.\n• Delete 18 dangling vias + 3 dangling track stubs.\n• Update PCB from Schematic: pulls U2 value\n   TJA1462A → TJA1051T/3 (footprint identical).\n• Outline fixed: connector mouth moved off Edge.Cuts.",fs=8)

fig.savefig("modules/12vhpwr-standard/12vhpwr-route-plan.png",dpi=145,facecolor="white")
print("wrote modules/12vhpwr-standard/12vhpwr-route-plan.png")
