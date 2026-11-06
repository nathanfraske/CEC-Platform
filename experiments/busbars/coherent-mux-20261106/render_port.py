"""Local actual-native copper comparison; no invented/approximate pad boxes."""
import json
from pathlib import Path
from repair_port import WORK,SOURCE,force,_native
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch


def main():
    p,_=_native();out=WORK/'port-repaired-v1'
    record=json.loads((out/'construction.json').read_text())
    paths=[SOURCE,Path(record['candidate'])]
    fig,axes=plt.subplots(1,2,figsize=(10,5),layout='constrained')
    for ax,path,title in zip(axes,paths,('Before: partial pad overlap','After: separate via + short dogbone')):
        board=p.LoadBoard(str(path));ax.set_facecolor('#14372c')
        for item in [*board.GetTracks(),*(pad for fp in board.GetFootprints()for pad in fp.Pads())]:
            if not item.IsOnLayer(p.F_Cu):continue
            bb=item.GetBoundingBox()
            if bb.GetRight()<11400000 or bb.GetLeft()>13700000 or bb.GetBottom()<47400000 or bb.GetTop()>49700000:continue
            poly=p.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,p.F_Cu,0,1000,p.ERROR_OUTSIDE)
            colour='#a6c6b8'if item.GetClass()=='PCB_TRACK'else '#d6dcb8'
            for i in range(poly.OutlineCount()):
                vertices=[];codes=[]
                rings=[poly.COutline(i)]+[poly.CHole(i,h)for h in range(poly.HoleCount(i))]
                for ring in rings:
                    points=[(ring.CPoint(j).x/1e6,ring.CPoint(j).y/1e6)for j in range(ring.PointCount())]
                    if not points:continue
                    vertices.extend(points+[points[0]])
                    codes.extend([MPath.MOVETO]+[MPath.LINETO]*(len(points)-1)+[MPath.CLOSEPOLY])
                if vertices:ax.add_patch(PathPatch(MPath(vertices,codes),facecolor=colour,edgecolor='none'))
        # Drill voids cut the final native copper union, including any pad
        # accidentally covering the old drill; drawing pads last hid that.
        for item in board.GetTracks():
            if item.GetClass()=='PCB_VIA':
                x,y=item.GetPosition();ax.add_patch(plt.Circle((x/1e6,y/1e6),item.GetDrillValue()/2e6,color='#14372c'))
        ax.set(xlim=(11.4,13.7),ylim=(49.7,47.4),aspect='equal',xlabel='Native x (mm)',ylabel='Native y (mm)')
        ax.set_title(title+'\nF.Cu / '+force._hash(path)[:12],fontsize=11)
        ax.text(13.3,48.13,'R54.1',fontsize=9,color='white')
        ax.text(13.3,49.15,'R54.2',fontsize=9,color='white')
    fig.suptitle('ATX private via repair — board outline and component placements unchanged',fontsize=12)
    target=out/'port-before-after.png';fig.savefig(target,dpi=160)
    print(str(target))


if __name__=='__main__':main()
