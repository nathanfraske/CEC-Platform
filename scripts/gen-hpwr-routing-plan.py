#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Generate the 12VHPWR Standard high-current per-pin INTERLEAVE + routing PLAN
# diagram (documentation — the actual copper is routed in the KiCad GUI). Shows:
# how the 6x +12V pins each get their own 1 mOhm shunt + INA240, why the shunts
# are staggered into two rows, how the 12V lanes stay equal-length (even current
# sharing = melt prevention), and the 4-layer copper strategy.
#   python3 scripts/gen-hpwr-routing-plan.py
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch, Circle

RED, GND, GOLD, INA = "#c0392b", "#2c3e50", "#f1c40f", "#aed6f1"
fig = plt.figure(figsize=(15.5, 9.2))
gs = fig.add_gridspec(1, 2, width_ratios=[1.75, 1.0], wspace=0.18)
axL = fig.add_subplot(gs[0]); axR = fig.add_subplot(gs[1])

# ============================ LEFT: top-down interleave ============================
axL.set_title("12VHPWR Standard — per-pin sense interleave & balanced 12V lanes (top view)",
              fontsize=12.5, fontweight="bold")
Px = [2, 5, 8, 11, 14, 17]          # six +12V pins, 3.0 mm pitch
yJ3, yGin = 100, 96.5
yA, yB = 80, 70                      # staggered shunt rows
yJ4, yGout = 14, 10.5

# GND plane backdrop
axL.add_patch(Rectangle((-3, 7), 28, 97, facecolor="0.88", edgecolor="none", zorder=0))
axL.text(22.4, 45, "GND\nIn1+In2\nsolid planes\n(common\nreturn)", ha="center", va="center",
         color="0.4", fontsize=8.5, zorder=1)

# ---- J3 input header ----
axL.add_patch(FancyBboxPatch((-1.2, 93.5), 21.4, 13, boxstyle="round,pad=0.3",
              facecolor="0.96", edgecolor="k", zorder=2))
axL.text(9.5, 110.5, "J3  PSU 12V-2×6 IN  (board-mount right-angle MALE header)",
         ha="center", fontsize=9.5, fontweight="bold")
for i, x in enumerate(Px):
    axL.add_patch(Circle((x, yJ3), 1.0, facecolor=RED, edgecolor="k", zorder=4))
    axL.text(x, yJ3, str(i + 1), ha="center", va="center", fontsize=6.5, color="white", zorder=5)
    axL.add_patch(Circle((x, yGin), 1.0, facecolor=GND, edgecolor="k", zorder=4))
axL.text(19.6, yJ3, "+12V ×6", va="center", fontsize=7.5, color=RED, fontweight="bold")
axL.text(19.6, yGin, "GND ×6", va="center", fontsize=7.5, color=GND)

# ---- six lanes: pin -> own shunt -> matching J4 pin (per-pin pass-through) ----
for i, x in enumerate(Px):
    ys = yA if i % 2 == 0 else yB
    axL.add_line(plt.Line2D([x, x], [yJ3 - 1, yJ4 + 1], color=RED, lw=3.4,
                 solid_capstyle="round", zorder=3))                      # the 12V lane
    axL.add_patch(Rectangle((x - 1.05, ys - 2.4), 2.1, 4.8, facecolor=GOLD,
                  edgecolor="k", zorder=5))                              # 1 mOhm shunt
    axL.text(x, ys + 3.6, f"RS{i+1}", ha="center", fontsize=6.8, zorder=6)
    axL.annotate("", xy=(x, ys - 3.6), xytext=(x, ys + 3.6),
                 arrowprops=dict(arrowstyle="-|>", color="#7b241c", lw=1.1), zorder=6)
    side = 1 if i % 2 == 0 else -1                                       # INA on alternating side
    inx = x + side * 1.7
    axL.add_patch(Rectangle((inx - 1.6 + (1.6 if side > 0 else -1.6), ys - 1.7),
                  3.2, 3.4, facecolor=INA, edgecolor="navy", zorder=5))
    bx = inx + side * 1.6
    axL.text(bx, ys + 2.7, f"U1{i}", ha="center", fontsize=5.6, color="navy", zorder=6)
    axL.add_line(plt.Line2D([x + side, bx - side * 1.6], [ys + 1.4, ys + 0.7],
                 color="navy", lw=0.7, zorder=6))                        # Kelvin +
    axL.add_line(plt.Line2D([x + side, bx - side * 1.6], [ys - 1.4, ys - 0.7],
                 color="navy", lw=0.7, zorder=6))                        # Kelvin -
    for vx in (-0.5, 0, 0.5):                                            # via field (lane <-> outers)
        axL.add_patch(Circle((x + vx * 0.7, 30), 0.22, facecolor="0.45", edgecolor="none", zorder=5))

# ---- J4 output pigtail land ----
axL.add_patch(FancyBboxPatch((-1.2, 6.5), 21.4, 12.5, boxstyle="round,pad=0.3",
              facecolor="0.96", edgecolor="k", zorder=2))
axL.text(9.5, 2.6, "J4  captive pigtail OUT  (12V-2×6 cable soldered → GPU)",
         ha="center", fontsize=9.5, fontweight="bold")
for i, x in enumerate(Px):
    axL.add_patch(Circle((x, yJ4), 1.0, facecolor=RED, edgecolor="k", zorder=4))
    axL.add_patch(Circle((x, yGout), 1.0, facecolor=GND, edgecolor="k", zorder=4))

axL.text(2.0, 30, "via field\n(12V → B.Cu)", ha="center", va="center", fontsize=6, color="0.3")
axL.set_xlim(-4, 25); axL.set_ylim(0, 114); axL.axis("off"); axL.set_aspect("equal")
# legend
axL.text(-3.5, -1.2,
         "RED = +12V lane (per pin)   GOLD = 1 mΩ shunt   BLUE = INA240 + Kelvin taps   "
         "DARK = GND pins / plane", fontsize=8)

# ============================ RIGHT: stackup + notes ============================
axR.set_title("4-layer stackup  +  current budget", fontsize=12.5, fontweight="bold")
stk = [("B.Cu  (2 oz)", RED, "12V lanes — paralleled, via-stitched"),
       ("dielectric", "0.82", ""),
       ("In2.Cu (1 oz)", GND, "GND plane"),
       ("dielectric (core)", "0.78", ""),
       ("In1.Cu (1 oz)", GND, "GND plane"),
       ("dielectric", "0.82", ""),
       ("F.Cu  (2 oz)", RED, "12V lanes + shunts + INA + signal")]
y = 0
for name, color, desc in stk:
    h = 1.0 if "Cu" in name else 1.7
    axR.add_patch(Rectangle((0, y), 7.5, h, facecolor=color, edgecolor="k",
                  alpha=0.55 if "diel" in name else 0.9))
    txt = name + (("  —  " + desc) if desc else "")
    axR.text(7.8, y + h / 2, txt, va="center", fontsize=8.2,
             color="white" if color == GND else "k",
             fontweight="bold" if "Cu" in name else "normal")
    y += h
axR.annotate("", xy=(3.7, y + 0.2), xytext=(3.7, -0.2),
             arrowprops=dict(arrowstyle="<->", color="0.3", lw=1.0))
axR.text(3.95, y / 2, "12V on both 2 oz outers,\nsandwiched by GND inners\n→ low loop inductance,\nbalanced lanes",
         va="center", fontsize=7.6, color="0.25")

notes = (
    "WHY INTERLEAVE\n"
    "• 600 W ÷ 12 V = 50 A over 6 pins ≈ 8.3 A/pin nominal.\n"
    "• Uneven sharing is what MELTS 12VHPWR — so each pin gets its\n"
    "  OWN 1 mΩ shunt + INA240, and the 6 lanes are kept equal-length\n"
    "  & symmetric so the module adds no imbalance (and detects any).\n\n"
    "SHUNT STAGGER\n"
    "• 2512 shunts (3.2 mm) won't fit the 3.0 mm pin pitch in one row\n"
    "  → stagger into 2 rows; lanes stay straight/vertical = matched.\n\n"
    "COPPER (design to the contact rating, not just nominal)\n"
    "• Micro-Fit+ contact ≈ 9.5–13.5 A → size lanes for ~13 A/pin.\n"
    "• 12V lane ≥ 2.5 mm on F.Cu, paralleled on B.Cu (both 2 oz).\n"
    "• 6–9× 0.5 mm vias per shunt→outer transition (~3 A each).\n"
    "• GND: solid In1+In2 planes + outer fills (50 A common return).\n\n"
    "SENSE\n"
    "• INA240A3 (gain 100): 1 mΩ×8.3 A×100 = 0.83 V; 13 A → 1.3 V.\n"
    "• Kelvin taps off the shunt terminal copper (§6.8), tight diff\n"
    "  pair to the INA — keep off the high-current path."
)
axR.text(0, -1.5, notes, va="top", ha="left", fontsize=8.0, family="monospace")
axR.set_xlim(0, 16); axR.set_ylim(-20, y + 1); axR.axis("off")

fig.suptitle("CEC 12VHPWR Standard — high-current per-pin routing plan (route copper in the KiCad GUI)",
             fontsize=11, y=0.985, color="0.3")
fig.savefig("modules/12vhpwr-standard/12vhpwr-routing-plan.png", dpi=130, bbox_inches="tight")
print("wrote modules/12vhpwr-standard/12vhpwr-routing-plan.png")
