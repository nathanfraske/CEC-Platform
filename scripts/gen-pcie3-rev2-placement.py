import sys, math
sys.path.insert(0,"scripts")
import pcbnew, cec_fr
MM=1e6
SRC="modules/pcie-8pin-3port/pcie8pin-3port-module.kicad_pcb"
DST="build/pcie3-rev2/pcie3-rev2.kicad_pcb"
INA238=["U10","U11","U12"]; INA181=["U20","U21","U22"]; TLV=["U30","U31","U32"]; SHUNT=["RS1","RS2","RS3"]
BACK=0.9; DX181=3.83; DY181=-1.2; DX30=4.1; DY30=3.0
b=pcbnew.LoadBoard(SRC)
fps={fp.GetReference():fp for fp in b.GetFootprints()}
for r in INA238:
    p=fps[r].GetPosition(); fps[r].SetPosition(pcbnew.VECTOR2I(int(p.x-BACK*MM),int(p.y)))
p=fps["H3"].GetPosition(); fps["H3"].SetPosition(pcbnew.VECTOR2I(int(p.x-0.6*MM),int(p.y)))
for si,ir,tr in zip(SHUNT,INA181,TLV):
    sp=fps[si].GetPosition()
    fps[ir].SetOrientationDegrees(-90)
    fps[ir].SetPosition(pcbnew.VECTOR2I(int(sp.x+DX181*MM),int(sp.y+DY181*MM)))
    fps[tr].SetPosition(pcbnew.VECTOR2I(int(sp.x+DX30*MM),int(sp.y+DY30*MM)))
# FULL all-pairs courtyard overlap
def cybb(fp):
    sh=fp.GetCourtyard(pcbnew.F_Cu)
    if sh.OutlineCount()==0: sh=fp.GetCourtyard(pcbnew.B_Cu)
    if sh.OutlineCount()==0: return None
    bb=sh.BBox(); return (bb.GetLeft()/MM,bb.GetTop()/MM,bb.GetRight()/MM,bb.GetBottom()/MM)
def ovl(a,c): return None if(a is None or c is None) else (not(a[2]<=c[0] or c[2]<=a[0] or a[3]<=c[1] or c[3]<=a[1]))
allf=list(b.GetFootprints()); hh=set()
for i,fp in enumerate(allf):
    a=cybb(fp)
    for fp2 in allf[i+1:]:
        if ovl(a,cybb(fp2)):
            x0=max(a[0],cybb(fp2)[0]); pass
            hh.add(tuple(sorted((fp.GetReference(),fp2.GetReference()))))
# compare to committed baseline overlaps
b0=pcbnew.LoadBoard(SRC); allf0=list(b0.GetFootprints()); hh0=set()
def cybb0(fp):
    sh=fp.GetCourtyard(pcbnew.F_Cu)
    if sh.OutlineCount()==0: sh=fp.GetCourtyard(pcbnew.B_Cu)
    if sh.OutlineCount()==0: return None
    bb=sh.BBox(); return (bb.GetLeft()/MM,bb.GetTop()/MM,bb.GetRight()/MM,bb.GetBottom()/MM)
for i,fp in enumerate(allf0):
    a=cybb0(fp)
    for fp2 in allf0[i+1:]:
        if ovl(a,cybb0(fp2)): hh0.add(tuple(sorted((fp.GetReference(),fp2.GetReference()))))
print("BASELINE overlaps (committed):",sorted(hh0))
print("REV2 overlaps:",sorted(hh))
print("NEW overlaps (rev2 not in baseline):",sorted(hh-hh0))
rep=cec_fr.synthesize_kelvin_taps(pcbnew.LoadBoard(SRC) if False else b)
print("TAPS laid=",rep["taps"]," refused=",sum(len(v) for v in rep.get("refused",{}).values()),rep.get("refused"))
b.Save(DST); print("SAVED",DST)
