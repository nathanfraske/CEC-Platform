"""Saved native F.Cu before/after only; no hypothetical copper or pose overlays."""
import sys,shutil
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_assembly_envelope as assembly
import cec_board_geometry as geometry
from shapely.geometry import box,Point
from shapely.geometry.polygon import orient
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as PlotPath
from matplotlib.patches import PathPatch,Patch
p,_=_native();folder=Path(__file__).parent
cases=[('Before: C37 shifted, original rail',folder/'hub-C37-vent-v1/candidate/board.kicad_pcb','4825def1abce879355b751406634f2dc5d552c207c779710b3cd6877ecf05992'),
 ('After: native-refilled octilinear widening',folder/'hub-C37-widen-v1/candidate/board.kicad_pcb','a977b5da70742f0e49b28f9a3d7499eb84ab0f9e508ab171d0604c2635832975')]
window=box(72.7,36.5,77.,48.5);net='/HOLD-UP + 3V3 REGULATOR/+5V_HOLD'
def draw(ax,g,color,edge=None,z=1):
 if g.is_empty:return
 if g.geom_type!='Polygon':
  for part in getattr(g,'geoms',[]):draw(ax,part,color,edge,z)
  return
 g=orient(g,sign=1);vertices=[];codes=[]
 for ring in [g.exterior,*g.interiors]:
  pts=list(ring.coords);vertices.extend(pts);codes.extend([PlotPath.MOVETO]+[PlotPath.LINETO]*(len(pts)-2)+[PlotPath.CLOSEPOLY])
 ax.add_patch(PathPatch(PlotPath(vertices,codes),facecolor=color,edgecolor=edge or color,lw=.35,zorder=z))
def color(name):return '#c78c24'if name==net else '#60988c'if name=='GND'else '#9d83b3'
fig,axes=plt.subplots(1,2,figsize=(8.1,10.6),sharex=True,sharey=True)
for ax,(title,path,sha)in zip(axes,cases):
 assert force._hash(path)==sha
 b=p.LoadBoard(str(path));material=assembly.polygon_from_native(geometry.outline_material(b)).intersection(window)
 draw(ax,material,'#f3f3ed',z=0)
 for zone in b.Zones():
  if zone.GetIsRuleArea()or not zone.HasFilledPolysForLayer(p.F_Cu):continue
  draw(ax,assembly.polygon_from_native(zone.GetFilledPolysList(p.F_Cu)).intersection(window),color(zone.GetNetname()),z=1)
 for t in b.GetTracks():
  if not t.IsOnLayer(p.F_Cu):continue
  poly=p.SHAPE_POLY_SET();t.TransformShapeToPolygon(poly,p.F_Cu,0,1000,p.ERROR_OUTSIDE)
  draw(ax,assembly.polygon_from_native(poly).intersection(window),color(t.GetNetname()),z=2)
  if t.GetClass()=='PCB_VIA':draw(ax,Point(t.GetPosition().x/1e6,t.GetPosition().y/1e6).buffer(t.GetDrillValue()/2e6,resolution=64).intersection(window),'white','#263946',z=4)
 for fp in b.GetFootprints():
  for pad in fp.Pads():
   if pad.IsOnLayer(p.F_Cu):draw(ax,assembly.polygon_from_native(pad.GetEffectivePolygon(p.F_Cu)).intersection(window),color(pad.GetNetname()),'#45453d',z=3)
   if pad.HasHole():
    poly=p.SHAPE_POLY_SET();pad.TransformHoleToPolygon(poly,0,1000,p.ERROR_OUTSIDE);draw(ax,assembly.polygon_from_native(poly).intersection(window),'white','#263946',z=4)
 ax.text(73.5,42.7,'C37.2\nGND',fontsize=9,ha='center',va='center',color='#173f36',zorder=6)
 ax.text(76.7,42.7,'+5V_HOLD',fontsize=8,ha='center',va='center',rotation=90,color='#67440e',zorder=6)
 ax.set_title(title+'\nSHA256 '+sha[:32]+'\n'+sha[32:],fontsize=8,pad=10,fontfamily='monospace')
 ax.set(xlim=(72.7,77.),ylim=(48.5,36.5),xlabel='Hub x / mm',aspect='equal');ax.set_xticks([73,74,75,76,77]);ax.grid(alpha=.2,zorder=0);ax.tick_params(labelsize=8)
 assert force._hash(path)==sha
axes[0].set_ylabel('Hub y / mm')
fig.suptitle('Actual saved F.Cu — same crop and 1:1 XY scale\nNative fill, pads, tracks and drilled holes; no hypothetical copper',fontsize=11,y=.98)
fig.legend(handles=[Patch(color='#c78c24',label='+5V_HOLD copper'),Patch(color='#60988c',label='GND copper'),Patch(facecolor='white',edgecolor='#263946',label='Drilled void')],loc='lower center',ncol=3,fontsize=9,bbox_to_anchor=(.5,.035))
fig.text(.5,.015,'Local geometric widening only — not current / thermal / release qualification',ha='center',fontsize=8)
fig.subplots_adjust(top=.87,bottom=.11,wspace=.17,left=.1,right=.97)
output=folder/'hub-C37-widen-native-before-after.png';fig.savefig(output,dpi=190,facecolor='white')
delivery=Path('/mnt/c/Users/Admin/Documents/CEC-Board-Reviews/hub-C37-widen-20261106.png');delivery.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(output,delivery)
print(output);print(delivery)
