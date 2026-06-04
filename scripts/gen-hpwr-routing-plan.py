#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Generate the 12VHPWR Standard high-current ROUTING PLAN diagram (documentation
# only -- the actual copper is laid in the KiCad GUI; routing is the CLAUDE/GUI
# boundary). It answers, with worked numbers, how the board's high-current and
# sense nets must be routed:
#   1. how the six +12V lanes run (straight, equal-length, F.Cu + B.Cu paralleled,
#      through the in-line per-pin shunt);
#   2. how the four-wire Kelvin sense pair runs off each shunt to its INA240 +
#      the RC input filter;
#   3. trace widths (IPC-2221, 2oz outer);
#   4. via stitching frequency (12V layer-paralleling + GND plane);
#   5. via sizes / ampacity.
# The left panel is drawn to the REAL placement (scripts/gen-module-pcb.py
# placement_hpwr): J3 (4,6.5), shunts RS1/3/5 @ y22 + RS2/4/6 @ y30, INA U10..U15
# @ y40/48, J4 (4,83.6); board 44 x 92, 4-layer 2oz/1oz.
#   python3 scripts/gen-hpwr-routing-plan.py
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch, Circle, FancyArrow

RED   = "#c0392b"   # +12V copper
DRED  = "#7b241c"
GNDC  = "#34495e"   # GND
GOLD  = "#f1c40f"   # shunt
INA   = "#aed6f1"   # INA240
NAVY  = "#1a5276"   # sense
VIA   = "#117a65"   # via
PALE  = "#f4f6f7"

# real board placement (mm, board origin top-left, y increases DOWNWARD)
H = 92.0
PX   = [4.0, 7.0, 10.0, 13.0, 16.0, 19.0]          # six +12V pin columns
yJ3  = 6.5                                          # J3 +12V pad row
yGND3 = 9.5                                         # J3 GND pad row
ySH  = [22.0 if i % 2 == 0 else 30.0 for i in range(6)]   # staggered shunt rows
yINA = [40.0 if i % 2 == 0 else 48.0 for i in range(6)]   # staggered INA rows
yJ4  = 83.6                                         # J4 +12V pad row
def py(yb): return H - yb                           # board-y -> plot-y (flip)

fig = plt.figure(figsize=(19.5, 11.6))
gs = fig.add_gridspec(3, 2, width_ratios=[1.06, 1.32], height_ratios=[1.18, 1.0, 1.18],
                      wspace=0.12, hspace=0.30)
axL = fig.add_subplot(gs[:, 0])      # tall left: top-down routing
axK = fig.add_subplot(gs[0, 1])      # Kelvin shunt detail
axS = fig.add_subplot(gs[1, 1])      # stackup cross-section
axT = fig.add_subplot(gs[2, 1])      # spec tables

# ======================================================================
# LEFT PANEL -- top-down routing of the 12V power section (to scale)
# ======================================================================
axL.set_title("12V power section — top-down routing (to real placement)",
              fontsize=11.5, fontweight="bold")
# board substrate (left power column shown; right half is ESP/control)
axL.add_patch(Rectangle((0, py(H)), 22.0, H, facecolor="#16432e", edgecolor="k", lw=1.4, zorder=0))
# GND plane stitch grid (faint)
for gx in [x for x in range(1, 22, 5)]:
    for gy in range(2, 92, 5):
        axL.add_patch(Circle((gx, py(gy)), 0.30, facecolor=VIA, edgecolor="none", alpha=0.28, zorder=1))

# ---- J3 header (overhangs the TOP edge) ----
axL.add_patch(FancyBboxPatch((1.4, py(yGND3) - 1.0), 19.2, 6.2, boxstyle="round,pad=0.15",
              facecolor="#0e2c1e", edgecolor="0.8", lw=1.0, zorder=2))
axL.text(11, py(yJ3) + 4.2, "J3  12V-2×6 IN  (shroud overhangs ↑)",
         ha="center", va="bottom", fontsize=7.8, fontweight="bold", color="w", zorder=6)
for i, x in enumerate(PX):
    axL.add_patch(Circle((x, py(yJ3)), 1.05, facecolor=RED, edgecolor="k", zorder=5))
    axL.text(x, py(yJ3), str(i + 1), ha="center", va="center", fontsize=6, color="w", zorder=6)
    axL.add_patch(Circle((x, py(yGND3)), 0.9, facecolor=GNDC, edgecolor="k", zorder=5))

# ---- six +12V lanes: J3 pin -> in-line shunt -> J4 pin (straight, equal length) ----
for i, x in enumerate(PX):
    axL.add_line(plt.Line2D([x, x], [py(yJ3), py(yJ4)], color=RED, lw=7.0,
                 solid_capstyle="butt", zorder=3, alpha=0.92))               # F.Cu lane
    axL.add_line(plt.Line2D([x, x], [py(yJ3), py(yJ4)], color="#fadbd8", lw=1.6,
                 ls=(0, (2, 2.4)), zorder=4))                                # B.Cu mirror
    # stitch pair every ~5 mm down the lane (12V F<->B paralleling)
    for sgy in range(int(yJ3) + 5, int(yJ4), 5):
        axL.add_patch(Circle((x, py(sgy)), 0.26, facecolor=VIA, edgecolor="k", lw=0.25, zorder=4))
    # in-line shunt (lane current passes through it) + via field at each terminal
    sy = ySH[i]
    axL.add_patch(Rectangle((x - 1.05, py(sy) - 2.6), 2.1, 5.2, facecolor=GOLD,
                  edgecolor="k", lw=0.8, zorder=6))
    axL.text(x, py(sy) + 4.4, f"RS{i+1}", ha="center", va="center", fontsize=6.0, zorder=7)
    for vy in (sy - 3.4, sy + 3.4):
        for k in range(3):
            axL.add_patch(Circle((x - 0.7 + k * 0.7, py(vy)), 0.32, facecolor=VIA,
                          edgecolor="k", lw=0.3, zorder=7))
    # INA240 (real position, lower band) + tight Kelvin pair down the inter-lane gap
    iy = yINA[i]
    axL.add_patch(Rectangle((x - 1.5, py(iy) - 2.0), 3.0, 4.0, facecolor=INA,
                  edgecolor=NAVY, lw=0.8, zorder=6))
    axL.text(x, py(iy), f"U1{i}", ha="center", va="center", fontsize=5.2, color=NAVY, zorder=7)
    gx = x + 1.45                                                            # pair in the gap
    axL.add_line(plt.Line2D([gx, gx], [py(sy + 2.2), py(iy - 1.6)], color=NAVY, lw=0.9, zorder=8))
    axL.add_line(plt.Line2D([gx + 0.45, gx + 0.45], [py(sy + 2.2), py(iy - 1.6)],
                 color=NAVY, lw=0.9, zorder=8))

# equal-length call-out (thin, right margin)
axL.annotate("", xy=(21.2, py(yJ3)), xytext=(21.2, py(yJ4)),
             arrowprops=dict(arrowstyle="<->", color="0.9", lw=1.0))
axL.text(20.7, py((yJ3 + yJ4) / 2), "6 lanes = equal length (≈77 mm) → balanced share",
         rotation=90, va="center", ha="center", fontsize=7.2, color="w")

# ---- J4 pigtail land (same rotation as J3 → lanes stay straight) ----
axL.add_patch(FancyBboxPatch((1.4, py(yJ4) - 3.2), 19.2, 6.0, boxstyle="round,pad=0.15",
              facecolor="#0e2c1e", edgecolor="0.8", lw=1.0, zorder=2))
for i, x in enumerate(PX):
    axL.add_patch(Circle((x, py(yJ4)), 1.05, facecolor=RED, edgecolor="k", zorder=5))
    for k in range(3):                                  # stitch each pin into both outers
        axL.add_patch(Circle((x - 0.7 + k * 0.7, py(yJ4 + 3.0)), 0.30, facecolor=VIA,
                      edgecolor="k", lw=0.3, zorder=6))
axL.text(11, py(yJ4) - 4.4, "J4  pigtail OUT → GPU",
         ha="center", va="top", fontsize=7.8, fontweight="bold", color="w")

# legend BELOW the board (outside the outline)
axL.text(11, -3.2,
         "RED = +12V lane (F.Cu 2oz)  ·  pink dashed = B.Cu 2oz mirror (paralleled)\n"
         "GOLD = 1 mΩ in-line shunt  ·  TEAL dots = vias (lane stitch + fields + GND grid)\n"
         "BLUE = INA240 (lower band)  ·  NAVY = tight Kelvin pair  →  see detail, top-right",
         fontsize=7.3, color="0.15", va="top", ha="center")
axL.set_xlim(-0.6, 22.8); axL.set_ylim(-9, H + 7); axL.axis("off"); axL.set_aspect("equal")

# ======================================================================
# KELVIN DETAIL (top-right)
# ======================================================================
axK.set_title("Four-wire Kelvin sense + INA240 input filter (§6.8)", fontsize=11, fontweight="bold")
# shunt 2512 with two terminal pads
axK.add_patch(Rectangle((3.0, 3.2), 1.6, 3.6, facecolor=GOLD, edgecolor="k", zorder=3))   # body
axK.add_patch(Rectangle((1.4, 2.8), 1.6, 4.4, facecolor="#b7950b", edgecolor="k", zorder=3))  # term A
axK.add_patch(Rectangle((4.6, 2.8), 1.6, 4.4, facecolor="#b7950b", edgecolor="k", zorder=3))  # term B
axK.text(3.8, 7.6, "1 mΩ shunt (R_2512)", ha="center", fontsize=8.5, fontweight="bold")
# FORCE (high current) to the OUTER ends
axK.add_patch(FancyArrow(0.1, 5.0, 1.2, 0, width=0.9, head_width=1.5, head_length=0.5,
              facecolor=RED, edgecolor="k", zorder=2))
axK.add_patch(FancyArrow(6.2, 5.0, 1.4, 0, width=0.9, head_width=1.5, head_length=0.5,
              facecolor=RED, edgecolor="k", zorder=2))
axK.text(0.7, 6.1, "+12V in\n(force)", ha="center", fontsize=7.5, color=DRED)
axK.text(7.4, 6.1, "+12V out\n(force)", ha="center", fontsize=7.5, color=DRED)
# SENSE taps off the INNER edges (right at the element)
axK.add_line(plt.Line2D([2.9, 2.9, 9.0], [4.0, 1.4, 1.4], color=NAVY, lw=1.6, zorder=4))
axK.add_line(plt.Line2D([4.7, 4.7, 9.0], [4.0, 0.7, 0.7], color=NAVY, lw=1.6, zorder=4))
axK.text(3.8, 2.05, "sense taps = INNER pad edges\n(exclude pad/solder/trace IR drop)",
         ha="center", fontsize=7.0, color=NAVY)
# RC filter at the INA
for yy, lab in ((1.4, "Rf 10Ω"), (0.7, "Rf 10Ω")):
    axK.add_patch(Rectangle((9.0, yy - 0.18), 1.1, 0.36, facecolor="w", edgecolor=NAVY, zorder=5))
axK.text(9.55, 1.95, "RFH/RFL\n2×10 Ω (matched)", ha="center", fontsize=6.8, color=NAVY)
axK.add_line(plt.Line2D([10.6, 10.6], [0.7, 1.4], color="k", lw=2.4, zorder=5))   # Cdiff
axK.add_line(plt.Line2D([10.35, 10.85], [1.18, 1.18], color="k", lw=1.2, zorder=5))
axK.add_line(plt.Line2D([10.35, 10.85], [0.92, 0.92], color="k", lw=1.2, zorder=5))
axK.text(11.0, 1.05, "CF 470 nF", fontsize=6.8, va="center")
axK.add_patch(Rectangle((11.9, 0.2, ), 2.0, 2.0, facecolor=INA, edgecolor=NAVY, lw=1.2, zorder=5))
axK.text(12.9, 1.2, "INA240A3\n×100", ha="center", va="center", fontsize=7.2, color=NAVY, zorder=6)
axK.annotate("", xy=(11.9, 1.05), xytext=(11.1, 1.05), arrowprops=dict(arrowstyle="->", color=NAVY))
axK.text(7.0, 8.9, "fc = 1/(2π·2·Rf·Cdiff) = 1/(2π·2·10·470n) ≈ 16.9 kHz   "
         "(10 kHz passes −1.3 dB)", fontsize=8, color="#1a5276", fontweight="bold")
axK.text(0.1, 9.7,
         "Sense pair carries ~no current → no IR drop → run it THIN (0.20–0.25 mm),\n"
         "as a TIGHT matched-length pair over the solid In1 GND plane, kept OFF and\n"
         "perpendicular to the 12V lanes. Rf + Cdiff placed AT the INA pins.",
         fontsize=7.3, va="top")
axK.set_xlim(0, 14.2); axK.set_ylim(0, 10.2); axK.axis("off")

# ======================================================================
# STACKUP CROSS-SECTION (mid-right)
# ======================================================================
axS.set_title("4-layer stackup — 12V on both 2oz outers, GND on both inners",
              fontsize=11, fontweight="bold")
rows = [("F.Cu — 2 oz (70 µm)", RED, "+12V lanes (2.5 mm) · shunts · INA · sense"),
        ("dielectric (prepreg) 0.20 mm", "0.82", ""),
        ("In1.Cu — 1 oz", GNDC, "GND plane (solid) — sense reference"),
        ("core 1.065 mm", "0.78", ""),
        ("In2.Cu — 1 oz", GNDC, "GND plane (solid) — return"),
        ("dielectric (prepreg) 0.20 mm", "0.82", ""),
        ("B.Cu — 2 oz (70 µm)", RED, "+12V lanes MIRRORED (paralleled, via-stitched)")]
y = 0
for name, col, desc in rows:
    h = 0.92 if "Cu" in name else 0.55
    axS.add_patch(Rectangle((0, y), 5.6, h, facecolor=col, edgecolor="k",
                  alpha=0.92 if "Cu" in name else 0.5))
    axS.text(5.85, y + h / 2, name + (("   —   " + desc) if desc else ""),
             va="center", fontsize=8.2, color="w" if col in (RED, GNDC) else "0.35",
             fontweight="bold" if "Cu" in name else "normal")
    y += h + 0.12
# F<->B stitch indicator
axS.annotate("", xy=(2.8, y - 0.2), xytext=(2.8, 0.2),
             arrowprops=dict(arrowstyle="<->", color="k", lw=1.0))
axS.text(2.95, y / 2, "12V F↔B\nstitched\n(both 2oz\nin parallel)", fontsize=7.2, va="center")
axS.text(0.0, -0.5, "Why: 12V on BOTH 2oz outers = max copper for 50A & inspectable. Stack is "
         "12V/GND/GND/12V,\nso the GND pair sits in the MIDDLE (sandwiched by the 12V outers); "
         "each 12V lane runs\nDIRECTLY against a GND plane (F.Cu→In1, B.Cu→In2) → return "
         "image-current right beneath\nit → small loop, low inductance + a quiet reference for "
         "the sense pair.\n"
         "NOTE: set BOTH inner pours to GND in the GUI — the shared generator stackup "
         "leaves In2's\ndefault net hint as 12V (a cable-board leftover); the pour net is "
         "chosen per-zone anyway.",
         fontsize=7.2, va="top", color="0.2")
axS.set_xlim(0, 12.0); axS.set_ylim(-2.4, y + 0.3); axS.axis("off")

# ======================================================================
# SPEC TABLES (bottom-right)  — widths / vias / stitching / budget
# ======================================================================
axT.axis("off"); axT.set_xlim(0, 1); axT.set_ylim(0, 1)
axT.set_title("Trace widths · via sizes · stitching · current budget",
              fontsize=11, fontweight="bold")

budget = (
    "CURRENT BUDGET\n"
    "• 600 W ÷ 12 V = 50 A over 6 pins = 8.3 A/pin nominal.\n"
    "• Design to the CONTACT rating, not nominal: Micro-Fit+ ≈ 9.5–13.5 A → 13 A/pin.\n"
    "• Shunt drop @1 mΩ: 8.3 A→8.3 mV (×100 = 0.83 V), 13 A→13 mV (1.30 V) into the ADC."
)
axT.text(0.0, 1.00, budget, va="top", ha="left", fontsize=7.9, family="monospace",
         bbox=dict(boxstyle="round,pad=0.4", facecolor="#fdf2e9", edgecolor="#ca6f1e"))

# width table (IPC-2221, external 2 oz)
wt = [
    ["NET", "WIDTH", "LAYER(S)", "RATING / NOTE"],
    ["+12V lane (per pin)", "2.5 mm", "F.Cu + B.Cu", "≈13 A @ <10 °C (2oz×2, paralleled)"],
    ["  (single-layer min)", "≥3.0 mm", "F.Cu (2oz)", "if a B.Cu mirror is interrupted"],
    ["GND return", "solid pour", "In1+In2+fill", "50 A distributed — never neck a plane"],
    ["Kelvin sense ± ", "0.20–0.25 mm", "F.Cu / In-ref", "~0 A; tight matched pair, off 12V"],
    ["INA OUT (ISENSE)", "0.25 mm", "F.Cu o/ GND", "to ESP ADC; away from 12V"],
    ["+3V3 (INA supply)", "0.30 mm", "F.Cu", "few mA per INA"],
]
# via table
vt = [
    ["VIA USE", "DRILL / PAD", "~AMPACITY", "QTY / SPACING"],
    ["12V F↔B (lane)", "0.50 / 0.90 mm", "~2 A @10°C", "pair every ~5 mm down each lane"],
    ["12V at shunt pad", "0.50 / 0.90 mm", "(~3 A @20°C)", "field of 5–6 per terminal"],
    ["12V at J3/J4 pin", "0.50 / 0.90 mm", "—", "3–6 around each THT power pin"],
    ["GND plane stitch", "0.50 / 0.90 mm", "—", "~5 mm grid; ~3 mm ring at conns"],
    ["GND guard / sense", "0.30 / 0.60 mm", "~1 A", "fence flanking the Kelvin pair"],
    ["signal (avoid on ±)", "0.30 / 0.60 mm", "~1 A", "only if a layer change is forced"],
]
def table(ax, rows, x0, y0, w, rh, head):
    cols = [0.0, 0.34, 0.56, 0.74, 1.0]
    for r, row in enumerate(rows):
        yy = y0 - r * rh
        if r == 0:
            ax.add_patch(Rectangle((x0, yy - rh), w, rh, transform=ax.transAxes,
                         facecolor=head, edgecolor="none", clip_on=False))
        for c, cell in enumerate(row):
            ax.text(x0 + cols[c] * w + 0.004, yy - rh * 0.62, cell, transform=ax.transAxes,
                    fontsize=6.9, fontweight="bold" if r == 0 else "normal",
                    color="w" if r == 0 else "0.1",
                    family="monospace")
        ax.plot([x0, x0 + w], [yy - rh, yy - rh], transform=ax.transAxes,
                color="0.7", lw=0.5, clip_on=False)

table(axT, wt, 0.0, 0.74, 1.0, 0.062, "#1a5276")
table(axT, vt, 0.0, 0.355, 1.0, 0.058, "#117a65")
axT.text(0.0, -0.02,
         "Stitch rule of thumb: keep F.Cu & B.Cu at the same potential and share current "
         "evenly →\nvia pair every ~5 mm along each 12V lane, dense (5–6) at every shunt "
         "terminal and\nconnector pin; tie In1/In2/outer GND on a ~5 mm grid (denser ring "
         "at J3/J4).",
         transform=axT.transAxes, fontsize=7.2, va="top", color="0.2")
axT.text(0.0, -0.20,
         "↳ These are PRE-LOADED as netclasses in the .kicad_pro (Power12V=2.5 mm/0.9-0.5 via, "
         "Sense=0.25 mm,\n   GND, Power, CAN, USB): routing a net auto-uses its width + via. "
         "0.25 & 2.5 mm widths and the\n   0.6/0.3 & 0.9/0.5 vias are in the dropdown menus. "
         "(The thin Kelvin tap shares the 12V net — draw\n   that short stub with the 0.25 mm "
         "preset by hand.)",
         transform=axT.transAxes, fontsize=7.0, va="top", color="#1a5276")

fig.suptitle("CEC 12VHPWR Standard — high-current + Kelvin-sense ROUTING PLAN  "
             "(route the copper in the KiCad GUI; this is the spec)",
             fontsize=12.5, y=0.995, color="0.25", fontweight="bold")
fig.savefig("modules/12vhpwr-standard/12vhpwr-routing-plan.png", dpi=145, bbox_inches="tight")
print("wrote modules/12vhpwr-standard/12vhpwr-routing-plan.png")
