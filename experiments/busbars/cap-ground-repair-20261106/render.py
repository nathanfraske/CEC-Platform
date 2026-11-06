"""Native copper and drill evidence for the exact saved local repair."""
import json
from pathlib import Path
from construct import WORK,SOURCE,PAD,VIA,force,_native
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as PlotPath
from matplotlib.patches import PathPatch


def main():
    p,_=_native();record=json.loads((WORK/'construction.json').read_text())
    paths=[SOURCE,Path(record['candidate'])]
    fig,axes=plt.subplots(1,2,figsize=(8,4.3),layout='constrained')
    for ax,path,title in zip(axes,paths,('Source: via land overhangs pad','Candidate: via land fully contained')):
        board=p.LoadBoard(str(path));ax.set_facecolor('#153b2d')
        pad=next(q for f in board.GetFootprints()for q in f.Pads()if force._uid(q)==PAD)
        via=next(v for v in board.GetTracks()if force._uid(v)==VIA)
        for item,colour in ((pad,'#d3d9b3'),(via,'#f2c65c')):
            poly=p.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,p.F_Cu,0,500,p.ERROR_OUTSIDE)
            for index in range(poly.OutlineCount()):
                points=poly.COutline(index)
                vertices=[(points.CPoint(j).x/1e6,points.CPoint(j).y/1e6)for j in range(points.PointCount())]
                vertices.append(vertices[0])
                codes=[PlotPath.MOVETO]+[PlotPath.LINETO]*(len(vertices)-2)+[PlotPath.CLOSEPOLY]
                ax.add_patch(PathPatch(PlotPath(vertices,codes),facecolor=colour,edgecolor='none'))
        at=via.GetPosition();ax.add_patch(plt.Circle((at.x/1e6,at.y/1e6),via.GetDrillValue()/2e6,color='#153b2d'))
        ax.set(xlim=(16.35,17.45),ylim=(47.28,46.25),aspect='equal',xlabel='Native x (mm)',ylabel='Native y (mm)')
        ax.set_title(title+'\n'+force._hash(path)[:12],fontsize=10)
    fig.suptitle('ATX C54 Ground — 0.10 mm correction, unchanged 0.50/0.30 mm via',fontsize=11)
    fig.savefig(WORK/'native-via-before-after.png',dpi=160)
    print(str(WORK/'native-via-before-after.png'))


if __name__=='__main__':main()
