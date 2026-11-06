"""Native F.Cu polygons; placement overlays never pretend to reroute copper."""
import sys,json
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_assembly_envelope as assembly
import cec_board_geometry as geometry
import cec_force_current as force
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path as PlotPath
from shapely.geometry import box,Point
from shapely.geometry.polygon import orient
from shapely.affinity import translate,rotate
p,_=_native();folder=Path(__file__).parent
records=[None,json.loads((folder/'geometry-coordinated-plus1p8.json').read_text()),json.loads((folder/'geometry-rejected-plus1.json').read_text())]
fixed='--fixed-ground'in sys.argv
if fixed:
 latest=json.loads((folder/'geometry-fixed-ground-pivot.json').read_text())
 latest['moves']={ref:((pose[0]-latest['source_poses'][ref][0])/1e6,(pose[1]-latest['source_poses'][ref][1])/1e6)for ref,pose in latest['proposed_poses'].items()}
 records=[None,latest]
source=ROOT/records[1]['source'];assert force._hash(source)==records[1]['source_sha256'];b=p.LoadBoard(str(source));window=box(9,43,26,55);fps=list(b.GetFootprints())
def polygon(item):
 poly=p.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,p.F_Cu,0,1000,p.ERROR_OUTSIDE)
 return assembly.polygon_from_native(poly)
def draw(ax,g,color,edge=None,alpha=1.,lw=.3,z=1,style='-'):
 if g.is_empty:return
 if g.geom_type!='Polygon':
  for q in getattr(g,'geoms',[]):draw(ax,q,color,edge,alpha,lw,z,style)
  return
 g=orient(g,sign=1.);vertices=[];codes=[]
 for ring in [g.exterior,*g.interiors]:
  pts=list(ring.coords);vertices.extend(pts);codes.extend([PlotPath.MOVETO]+[PlotPath.LINETO]*(len(pts)-2)+[PlotPath.CLOSEPOLY])
 ax.add_patch(PathPatch(PlotPath(vertices,codes),facecolor=color,edgecolor=edge or color,alpha=alpha,lw=lw,zorder=z,linestyle=style))
material=assembly.polygon_from_native(geometry.outline_material(b)).intersection(window)
copper=[];holes=[];padrows=[];courts=[]
for z in b.Zones():
 if z.GetIsRuleArea()or not z.IsOnLayer(p.F_Cu)or not z.IsFilled()or not z.HasFilledPolysForLayer(p.F_Cu):continue
 g=assembly.polygon_from_native(z.GetFilledPolysList(p.F_Cu)).intersection(window)
 if not g.is_empty:copper.append((g,z.GetNetname(),'zone'))
for t in b.GetTracks():
 if not t.IsOnLayer(p.F_Cu):continue
 if t.GetClass()=='PCB_VIA':
  if window.contains(Point(t.GetPosition().x/1e6,t.GetPosition().y/1e6)):
   holes.append(Point(t.GetPosition().x/1e6,t.GetPosition().y/1e6).buffer(t.GetDrillValue()/2e6,resolution=48))
 g=polygon(t).intersection(window)
 if not g.is_empty:copper.append((g,t.GetNetname(),'track'))
for fp in fps:
 try:courts.append((fp,assembly.footprint_planar_envelope(fp)[0]))
 except ValueError:pass
 for q in fp.Pads():
  if q.HasHole():
   poly=p.SHAPE_POLY_SET();q.TransformHoleToPolygon(poly,0,1000,p.ERROR_OUTSIDE);holes.append(assembly.polygon_from_native(poly))
  if q.IsOnLayer(p.F_Cu):padrows.append((fp,q,assembly.polygon_from_native(q.GetEffectivePolygon(p.F_Cu))))
def posed(g,fp,record):
 if record is None:return g
 ref=fp.GetReference();delta=record['moves'].get(ref,(0,0))
 if ref in record.get('proposed_poses',{}):
  turn=record['proposed_poses'][ref][2]-record['source_poses'][ref][2]
  g=rotate(g,-turn,origin=(fp.GetPosition().x/1e6,fp.GetPosition().y/1e6))
 return translate(g,*delta)
fig,axes=plt.subplots(1,len(records),figsize=(14 if fixed else 20,6.2),layout='constrained');fig.patch.set_facecolor('#f5f6f8')
titles=['Saved source F.Cu','Five +2X; C55 +1.8X; C51 fixed','Rejected four +1X; C54/C55 fixed']
if fixed:titles=['Saved source F.Cu','Latest: five +2X; C55 pivot about fixed Ground pad']
for ax,record,title in zip(axes,records,titles):
 moves={}if record is None else record['moves'];draw(ax,material,'#e4eadf',z=0)
 for g,net,kind in copper:
  color='#d3a34d'if net=='+5VSB'else '#658c87'if net=='GND'else '#8a8278'
  draw(ax,g,color,alpha=.6 if kind=='zone'else .9,z=1)
 for fp,q,g in padrows:
  if not g.intersects(window):continue
  draw(ax,g.intersection(window),'#b29560',alpha=.35 if fp.GetReference()in moves else .9,z=2)
 for hole in holes:draw(ax,hole.intersection(window),'#fff',edge='#4a555a',lw=.25,z=3)
 for fp,court in courts:
  ref=fp.GetReference();delta=moves.get(ref,(0,0));g=posed(court,fp,record)
  if not g.intersects(window):continue
  draw(ax,g.intersection(window),'none',edge='#0c6291'if ref in moves else '#48505a',lw=.65,z=4,style='--'if ref in moves else '-')
  if ref not in {'U6','C9','C27','R54','C54','C55','C51'}:continue
  x,y=fp.GetPosition().x/1e6+delta[0],fp.GetPosition().y/1e6+delta[1]
  ax.text(x,y-.7,ref,ha='center',va='bottom',fontsize=7,color='#173b55',zorder=7,bbox=dict(facecolor='white',edgecolor='none',alpha=.7,pad=.5))
 for fp,q,g in padrows:
  ref=fp.GetReference();delta=moves.get(ref,(0,0));g=posed(g,fp,record)
  if ref in moves:draw(ax,g.intersection(window),'#43c3d0',edge='#065864',lw=.5,z=5)
  if ref in {'U6','C9','C27','R54','C54','C55','C51'}and g.intersects(window):
   center=posed(Point(q.GetPosition().x/1e6,q.GetPosition().y/1e6),fp,record)
   ax.text(center.x,center.y,q.GetNumber(),ha='center',va='center',fontsize=5.5,color='#142d38',zorder=8)
 if record:
  for row in record.get('source_native_pad_or_dogbone_barrels',[]):
   if 'destination_mm'in row:
    x,y=row['destination_mm'];ax.plot(x,y,'o',ms=4,mfc='none',mec='#a31569',mew=.7,zorder=6)
  for collision in record['courtyard_collisions']:
   if collision['refs']==['U6','C54']:
    ax.annotate('COURTYARD OVERLAP',(16.9,47.0),(20,44),fontsize=7,color='#ac2233',arrowprops=dict(arrowstyle='->',color='#ac2233'),zorder=10)
 if record is records[1]and not fixed:ax.annotate('Old x22 +5VSB trunk intersects\nproposed C55 GND land',(22.2,48),(21,53.7),fontsize=7,color='#ac2233',ha='center',arrowprops=dict(arrowstyle='->',color='#ac2233'),zorder=10)
 if record is records[1]and fixed:ax.annotate('C55 Ground pad + original tail/via retained\nNo new holes; copper still NOT rerouted',(20.4,48),(20.7,53.7),fontsize=7,color='#075a50',ha='center',arrowprops=dict(arrowstyle='->',color='#075a50'),zorder=10)
 ax.set(xlim=(9,26),ylim=(55,43),aspect='equal',title=title,xlabel='native x (mm)',ylabel='native y (mm)');ax.grid(alpha=.16)
legend='Native F.Cu pads/tracks/pours + native courtyard outlines; cyan = proposed pads; original copper and holes retained'if fixed else 'Native F.Cu pads/tracks/pours + native courtyard outlines; cyan = proposed pads, magenta rings = proposed source-matched via axes'
fig.suptitle('PLACEMENT STUDY — COPPER NOT REROUTED\n'+legend,fontsize=11)
target=folder/('native-local-fixed-ground-pivot.png'if fixed else 'native-local-placement-study.png')
fig.savefig(target,dpi=180)
assert force._hash(source)==records[1]['source_sha256']
print(str(target))
