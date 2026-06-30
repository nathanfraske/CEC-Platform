import sys, math, shutil, os
sys.path.insert(0, "scripts")
import pcbnew
MM = 1e6
SRC = "modules/pcie-8pin-2port/pcie8pin-2port-module.kicad_pcb"
OUTDIR = "build/pcie2-inrow"
os.makedirs(OUTDIR, exist_ok=True)
DST = OUTDIR + "/pcie2-inrow.kicad_pcb"
shutil.copy(SRC, DST)
for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
    s = SRC[:-len(".kicad_pcb")] + ext
    if os.path.exists(s):
        shutil.copy(s, DST[:-len(".kicad_pcb")] + ext)

b = pcbnew.LoadBoard(DST)
# in-row sensing band at y=22, mirroring eps n2 offsets (INA238 -6.7, INA181 +3.8 rot-90, TLV +8.1)
# shunts kept at RS1=17.5, RS2=40.5
moves = {
    # ref : (x, y, rot_deg)
    "U10": (10.80, 22.00, 0),     # INA238 cable1 (backed off shunt 6.7mm)
    "U20": (21.33, 22.00, 270),   # INA181 cable1 in-row rot-90
    "U30": (25.58, 22.00, 0),     # TLV cable1 in-row
    "U11": (33.79, 22.00, 0),     # INA238 cable2
    "U21": (44.33, 22.00, 270),   # INA181 cable2 in-row rot-90
    "U31": (48.58, 22.00, 0),     # TLV cable2 in-row
    # detection decoupling caps -> clear of both HI/LO corridors + tap channels
    "C10": (11.50, 19.50, 0),     # U10 decouple, above-right of U10 (notch, clear of HI corridor 18.75)
    "C11": (34.50, 19.50, 0),     # U11 decouple
    "C20": (29.50, 20.00, 0),     # U20 decouple, clear column x24.6..33
    "C30": (29.50, 24.00, 0),     # U30 decouple, clear column
    "C21": (50.80, 20.00, 0),     # U21 decouple, between U31 and ESP cluster
    "C31": (50.80, 24.00, 0),     # U31 decouple
}
fps = {f.GetReference(): f for f in b.GetFootprints()}
for ref, (x, y, r) in moves.items():
    f = fps[ref]
    f.SetPosition(pcbnew.VECTOR2I(int(x*MM), int(y*MM)))
    f.SetOrientationDegrees(r)
# Remove decorative B.Cu CEC logo (no-net copper that collides with the dense detection->ESP B.Cu
# signal bundle; no clear 13x12mm B.Cu region exists on this board). Mirrors the proven eps-rev3-n2
# re-place, whose gate-clean board also carries no logo. Purely cosmetic; not a locked/electrical part.
if "LOGO1" in fps:
    b.Delete(fps["LOGO1"])
    print("removed LOGO1 (decorative B.Cu copper)")
# SW1 BOOT: rotate 180 so the /GPIO0 pad faces the ESP (eps did the same to shorten that net)
if "SW1" in fps:
    fps["SW1"].SetOrientationDegrees(180)
# clear any stale fills so DRC isn't fooled
for z in b.Zones():
    z.UnFill()
b.Save(DST)
print("WROTE", DST)

# courtyard overlap check (pairwise) + foreign part on pour-corridor band check
def crtyd_bbox(f):
    bb = f.GetCourtyard(pcbnew.F_Cu).BBox()
    if bb.GetWidth() == 0:
        bb = f.GetBoundingBox(False, False)
    return bb
boards = list(b.GetFootprints())
ov = []
for i in range(len(boards)):
    for j in range(i+1, len(boards)):
        a, c = boards[i], boards[j]
        ba, bc = crtyd_bbox(a), crtyd_bbox(c)
        if ba.Intersects(bc):
            # ignore mount/logo
            ov.append((a.GetReference(), c.GetReference()))
print("courtyard overlaps:", len(ov))
for o in ov[:30]:
    print("   ", o)
