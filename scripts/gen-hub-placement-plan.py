#!/usr/bin/env python3
"""Top-down placement floorplan for the Hub Standard pre-fab finish pass.

Draws the current board (outline + already-placed footprints, read live from the
.kicad_pcb) plus the PROPOSED positions for the 20 parts that "Update PCB from
Schematic" will bring in (the §2.9 power-switch cluster, the J7 NanoKVM-aux
cluster, and the board-temp NTC). Proposed boxes are courtyard-overlap-checked
against the existing placement so the plan is collision-clean before it is applied
in KiCad. PLAN artifact only -- it touches no board geometry.

  python3 scripts/gen-hub-placement-plan.py        # -> .svg (+ .png via cairosvg)
"""
import os, re, subprocess

PCB = "hubs/hub-standard/hub-standard.kicad_pcb"
SVG = "hubs/hub-standard/hub-standard-placement-plan.svg"
PNG = "hubs/hub-standard/hub-standard-placement-plan.png"

# ---- approximate courtyard W x H (mm, unrotated) keyed by footprint name ----
SIZE = {
    "ESP32-S3-WROOM-1": (18.0, 25.5), "RJ45_FTP_Shielded_Horizontal": (16.0, 16.0),
    "RUX0012A": (3.6, 3.6), "SOIC-8_3.9x4.9mm_P1.27mm": (6.0, 5.0),
    "SOT-23-5": (3.0, 3.0), "SOT-23-6": (3.0, 3.0), "SOT-23": (3.0, 3.0),
    "D_SMA": (5.2, 2.8), "D_SOD-323": (2.5, 1.7),
    "CP_Elec_16x17.5": (18.0, 19.0), "CP_Elec_6.3x7.7": (7.2, 8.6),
    "C_0603_1608Metric": (2.2, 1.4), "C_0402_1005Metric": (1.5, 1.0),
    "R_0402_1005Metric": (1.5, 1.0), "NTC_0402_1005Metric": (1.5, 1.0),
    "LED_SK6812MINI_PLCC4_3.5x3.5mm_P1.75mm": (3.8, 3.8),
    "JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal": (7.6, 11.5),
    "CEC_NANOKVM_AUX_5P": (12.0, 6.5),
    "USB_C_Receptacle_XKB_U262-16XN-4BVC11": (9.0, 11.0),
    "Panasonic_EVQPUJ_EVQPUA": (4.0, 3.5), "TestPoint_Pad_D1.5mm": (2.5, 2.5),
    "Fiducial_1mm_Mask2mm": (2.0, 2.0), "MountingHole_3.2mm_M3_Pad_Via": (7.0, 7.0),
    "CEC_Logo_Copper": (10.0, 10.0),
}
def box(x, y, rot, fp):
    w, h = SIZE.get(fp, (2.0, 2.0))
    if rot in (90, -90, 270): w, h = h, w
    return (x - w/2, y - h/2, x + w/2, y + h/2)
def overlap(a, b, m=0.15):
    return not (a[2] < b[0]+m or b[2] < a[0]+m or a[3] < b[1]+m or b[3] < a[1]+m)

# ---- read existing footprints from the PCB ----
pcb = open(PCB).read()
existing = []
for mm in re.finditer(r'\(footprint "([^"]+)"', pcb):
    op = mm.start(); d = 0; i = op; instr = esc = False
    while i < len(pcb):
        c = pcb[i]
        if instr:
            if esc: esc = False
            elif c == '\\': esc = True
            elif c == '"': instr = False
        else:
            if c == '"': instr = True
            elif c == '(': d += 1
            elif c == ')':
                d -= 1
                if d == 0: break
        i += 1
    blk = pcb[op:i+1]; fp = mm.group(1).split(':')[-1]
    at = re.search(r'\(at ([\-0-9.]+) ([\-0-9.]+)(?: ([\-0-9.]+))?\)', blk)
    ref = re.search(r'(?:property "Reference"|fp_text reference) "([^"]+)"', blk)
    existing.append((ref.group(1), float(at.group(1)), float(at.group(2)),
                     float(at.group(3) or 0), fp))

# ---- proposed new placements: (ref, x, y, rot, footprint, cluster) ----
PWR, AUX, NTC = "pwr", "aux", "ntc"
proposed = [
    ("U7",      149.5, 120.5,  0, "RUX0012A", PWR),
    ("C15",     146.5, 120.5,  0, "C_0402_1005Metric", PWR),
    ("C_SS2",   131.0, 144.5,  0, "C_0603_1608Metric", PWR),
    ("R_ILIM2", 133.0, 144.5,  0, "R_0402_1005Metric", PWR),
    ("R15",     135.0, 144.5,  0, "R_0402_1005Metric", PWR),
    ("R16",     131.0, 146.7,  0, "R_0402_1005Metric", PWR),
    ("R17",     133.0, 146.7,  0, "R_0402_1005Metric", PWR),
    ("R18",     135.0, 146.7,  0, "R_0402_1005Metric", PWR),
    ("J8",      164.0, 149.0, 90, "JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal", PWR),
    ("TH1",     139.0, 122.5,  0, "NTC_0402_1005Metric", NTC),
    ("R25",     141.0, 122.5,  0, "R_0402_1005Metric", NTC),
    ("C16",     140.0, 124.5,  0, "C_0402_1005Metric", NTC),
    ("J7",       88.0, 161.5,  0, "CEC_NANOKVM_AUX_5P", AUX),
    ("D7",       81.0, 156.0,  0, "D_SOD-323", AUX),
    ("R19",      84.0, 156.0,  0, "R_0402_1005Metric", AUX),
    ("R20",      86.0, 156.0,  0, "R_0402_1005Metric", AUX),
    ("R21",      88.0, 156.0,  0, "R_0402_1005Metric", AUX),
    ("R22",      90.0, 156.0,  0, "R_0402_1005Metric", AUX),
    ("R23",      92.0, 156.0,  0, "R_0402_1005Metric", AUX),
    ("R24",      94.0, 156.0,  0, "R_0402_1005Metric", AUX),
]

# ---- collision check ----
warn = []
for ref, x, y, rot, fp, cl in proposed:
    pb = box(x, y, rot, fp)
    for eref, ex, ey, erot, efp in existing:
        if overlap(pb, box(ex, ey, erot, efp)):
            warn.append(f"  OVERLAP  {ref} <-> existing {eref} ({efp})")
for i, (r1, x1, y1, t1, f1, c1) in enumerate(proposed):
    for (r2, x2, y2, t2, f2, c2) in proposed[i+1:]:
        if overlap(box(x1, y1, t1, f1), box(x2, y2, t2, f2)):
            warn.append(f"  OVERLAP  {r1} <-> {r2} (both proposed)")
print("COLLISION CHECK:", "CLEAN" if not warn else f"{len(warn)} hit(s)")
for w in warn: print(w)

# ---- emit SVG ----
xmin, xmax, ymin, ymax = 70, 168, 92, 164; SC = 9; M = 46; TOP = 56
W = int((xmax-xmin)*SC) + 2*M; H = int((ymax-ymin)*SC) + 2*M + TOP
def X(x): return round((x-xmin)*SC)+M
def Y(y): return round((y-ymin)*SC)+M+TOP
COL = {PWR: ("#1f6fe0", "#dbe9ff"), AUX: ("#1a9850", "#d7f0dd"), NTC: ("#d6320a", "#ffe0d6")}
s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
     f'font-family="DejaVu Sans, Arial, sans-serif">',
     f'<rect width="{W}" height="{H}" fill="white"/>',
     f'<text x="{M}" y="22" font-size="19" font-weight="bold">Hub Standard — '
     f'proposed placement for the 20 parts from Update-from-Schematic</text>',
     f'<text x="{M}" y="42" font-size="13" fill="#555">grey = already placed '
     f'&#160;&#160; <tspan fill="#1f6fe0">blue = §2.9 power-switch</tspan> '
     f'&#160;&#160; <tspan fill="#1a9850">green = J7 NanoKVM-aux</tspan> '
     f'&#160;&#160; <tspan fill="#d6320a">red = board-temp NTC</tspan></text>']
# board outline
s.append(f'<rect x="{X(xmin)}" y="{Y(ymin)}" width="{X(xmax)-X(xmin)}" '
         f'height="{Y(ymax)-Y(ymin)}" fill="none" stroke="black" stroke-width="3"/>')
# existing
for ref, x, y, rot, fp in existing:
    b = box(x, y, rot, fp)
    if "MountingHole" in fp:
        cx, cy = X(x), Y(y)
        s.append(f'<circle cx="{cx}" cy="{cy}" r="{round((b[2]-b[0])/2*SC)}" '
                 f'fill="none" stroke="#888" stroke-width="2"/>'); continue
    rj = fp.startswith("RJ45")
    s.append(f'<rect x="{X(b[0])}" y="{Y(b[1])}" width="{X(b[2])-X(b[0])}" '
             f'height="{Y(b[3])-Y(b[1])}" fill="{"#fff4dd" if rj else "#eeeeee"}" '
             f'stroke="{"#c8961e" if rj else "#aaaaaa"}" stroke-width="1"/>')
    if SIZE.get(fp, (0,0))[0] >= 3 or fp.startswith(("RJ45","JST","USB","ESP")):
        s.append(f'<text x="{X(x)}" y="{Y(y)+3}" font-size="9" fill="#777" '
                 f'text-anchor="middle">{ref}</text>')
# proposed
for ref, x, y, rot, fp, cl in proposed:
    b = box(x, y, rot, fp); ec, fc = COL[cl]
    s.append(f'<rect x="{X(b[0])}" y="{Y(b[1])}" width="{X(b[2])-X(b[0])}" '
             f'height="{Y(b[3])-Y(b[1])}" fill="{fc}" stroke="{ec}" stroke-width="2"/>')
    s.append(f'<text x="{X(x)}" y="{Y(b[3])+12}" font-size="12" fill="{ec}" '
             f'font-weight="bold" text-anchor="middle">{ref}</text>')
s.append('</svg>')
open(SVG, "w").write("\n".join(s))
print("wrote", SVG)
try:
    subprocess.run(["cairosvg", SVG, "-o", PNG], check=True)
    print("wrote", PNG)
except Exception as e:
    print("cairosvg rasterize skipped:", e)
