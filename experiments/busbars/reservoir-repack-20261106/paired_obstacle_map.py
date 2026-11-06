"""Exact source/model geometry, no proposal search or saved PCB mutation."""
import sys,json,math
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_assembly_envelope as assembly
import cec_board_geometry as geometry
from shapely.geometry import shape,mapping,box,Point
from shapely.affinity import affine_transform,translate
from shapely.ops import unary_union
from shapely.geometry.polygon import orient
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as PlotPath
from matplotlib.patches import PathPatch,Rectangle
p,_=_native();folder=Path(__file__).parent;source=ROOT/'experiments/busbars/cap-ground-repair-20261106/candidate/board.kicad_pcb';peer=ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb';stack=ROOT/'beta/assembly/hub-atx-stack.json';sha=force._hash(source);assert sha=='1512d4f046daebaba629ac29db4bc5caf2d53bc6ccf370e44deb903c4259b045';assert force._hash(peer)=='c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db';b=p.LoadBoard(str(source));hub=p.LoadBoard(str(peer));contract=json.loads(stack.read_text());spec=dict(contract.get('envelopes',{}))
for group in contract['envelope_groups']:
 for key in group['footprints']:spec[key]={k:v for k,v in group.items()if k!='footprints'}
data=assembly.extract(b,spec);hd=assembly.extract(hub,spec);c37=next(q for q in hd['bodies']if q['ref']=='C37');c37shape=affine_transform(shape(c37['xy']),contract['transform']);allowance=contract['xy_allowance_each_mm'];combined_guard=c37shape.buffer(2*allowance);window=box(9,43,26,55);material=assembly.polygon_from_native(geometry.outline_material(b)).intersection(window);fps={f.GetReference():f for f in b.GetFootprints()};courts={}
for ref,fp in fps.items():
 try:courts[ref]=assembly.footprint_planar_envelope(fp)[0]
 except ValueError:pass
moved_u6=translate(courts['U6'],2,0);fixed_geometries=[g for ref,g in courts.items()if ref not in {'U6','C54','C55','C51'}and fps[ref].GetLayer()==p.F_Cu];point_free=material.difference(unary_union([combined_guard,moved_u6,*fixed_geometries]));example=p.LoadBoard(str(source));ef=next(f for f in example.GetFootprints()if f.GetReference()=='C51');ef.SetOrientationDegrees(270);ef.SetPosition(p.VECTOR2I(17725000,51025000));example_shape=assembly.footprint_planar_envelope(ef)[0];distance=example_shape.distance(c37shape);source_distance=courts['C51'].distance(c37shape);gap=contract['gap_mm'];height=3.;free=gap[0]-c37['height_max_mm']-height;vent=c37['vent_min_mm'];hub_c37_fp=next(f for f in hub.GetFootprints()if f.GetReference()=='C37');hcourt=assembly.footprint_planar_envelope(hub_c37_fp)[0];neighbors=[]
for fp in hub.GetFootprints():
 if fp.GetReference()=='C37'or fp.GetLayer()!=hub_c37_fp.GetLayer():continue
 try:g=assembly.footprint_planar_envelope(fp)[0]
 except ValueError:continue
 neighbors.append(dict(ref=fp.GetReference(),native_courtyard_distance_mm=hcourt.distance(g),native_courtyard=mapping(g)))
neighbors.sort(key=lambda q:q['native_courtyard_distance_mm'])
def draw(ax,g,color,edge=None,alpha=1.,lw=.4,z=1,style='-'):
 if g.is_empty:return
 if g.geom_type!='Polygon':
  for q in getattr(g,'geoms',[]):draw(ax,q,color,edge,alpha,lw,z,style)
  return
 g=orient(g,sign=1);vertices=[];codes=[]
 for ring in[g.exterior,*g.interiors]:
  pts=list(ring.coords);vertices+=pts;codes +=[PlotPath.MOVETO]+[PlotPath.LINETO]*(len(pts)-2)+[PlotPath.CLOSEPOLY]
 ax.add_patch(PathPatch(PlotPath(vertices,codes),facecolor=color,edgecolor=edge or color,alpha=alpha,lw=lw,zorder=z,linestyle=style))
fig,axes=plt.subplots(2,2,figsize=(14,10),layout='constrained');relevant=[]
for ax,lid,title in [(axes[0,0],p.F_Cu,'Actual F.Cu: saved copper; +2X U6 courtyard overlay'),(axes[0,1],p.B_Cu,'Actual B.Cu: full-width power copper + drill constraints')]:
 draw(ax,material,'#e1eadd',z=0)
 for z in b.Zones():
  if z.GetIsRuleArea()or not z.IsOnLayer(lid)or not z.IsFilled()or not z.HasFilledPolysForLayer(lid):continue
  poly=assembly.polygon_from_native(z.GetFilledPolysList(lid)).intersection(window)
  draw(ax,poly,'#78a187'if z.GetNetname()=='GND'else '#d7ac58',alpha=.5)
 for t in b.GetTracks():
  if not t.IsOnLayer(lid):continue
  poly=p.SHAPE_POLY_SET();t.TransformShapeToPolygon(poly,lid,0,1000,p.ERROR_OUTSIDE);g=assembly.polygon_from_native(poly).intersection(window)
  if g.is_empty:continue
  net=t.GetNetname();color='#c99037'if net=='+5VSB'else '#537f9c'if net=='/SENSE3V3_HI'else '#708f82'if net=='GND'else '#8d827d';draw(ax,g,color,alpha=.8)
  if t.GetClass()=='PCB_VIA':draw(ax,Point(t.GetPosition().x/1e6,t.GetPosition().y/1e6).buffer(t.GetDrillValue()/2e6,resolution=48).intersection(window),'white',edge='#45535a',z=4)
  if lid==p.F_Cu:relevant.append(dict(uuid=force._uid(t),kind=t.GetClass(),net=net,geometry=mapping(g)))
 for ref,fp in fps.items():
  for pad in fp.Pads():
   if pad.IsOnLayer(lid):draw(ax,assembly.polygon_from_native(pad.GetEffectivePolygon(lid)).intersection(window),'#b89b62',alpha=.8,z=2)
   if pad.HasHole():
    poly=p.SHAPE_POLY_SET();pad.TransformHoleToPolygon(poly,0,1000,p.ERROR_OUTSIDE);draw(ax,assembly.polygon_from_native(poly).intersection(window),'white',edge='#45535a',z=4)
 for ref in ['U6','C54','C55','C51']:
  draw(ax,courts[ref].intersection(window),'none',edge='#1b3b49',lw=.7,z=5);x,y=fps[ref].GetPosition().x/1e6,fps[ref].GetPosition().y/1e6;ax.text(x,y,ref,fontsize=8,ha='center',zorder=8,bbox=dict(facecolor='white',alpha=.75,edgecolor='none',pad=.3))
 draw(ax,moved_u6.intersection(window),'none',edge='#005ec7',lw=1.1,z=6,style='--');ax.set_title(title,fontsize=10)
for ax in [axes[0,0],axes[0,1],axes[1,0]]:ax.set(xlim=(9,26),ylim=(55,43),aspect='equal',xlabel='ATX native x / mm',ylabel='ATX native y / mm');ax.grid(alpha=.15)
ax=axes[1,0];draw(ax,material,'#f4f4ef',z=0);draw(ax,point_free,'#c9e5cc',alpha=.9);draw(ax,c37shape.intersection(window),'#e5a746',alpha=.4);draw(ax,combined_guard.intersection(window),'none',edge='#b44b27',lw=1.2,style='--');draw(ax,moved_u6,'none',edge='#005ec7',lw=1.1);draw(ax,courts['C51'],'none',edge='#15583a',lw=1.3);draw(ax,example_shape,'none',edge='#b22266',lw=1.3);ax.text(21.6,54.4,'C37 actual model\ncenter (12.5,59.4)\nDmax18.5; XY pair allowance0.3',fontsize=7,ha='center',color='#783513');ax.text(17.9,50.1,'source C51',fontsize=7,color='#15583a');ax.text(18.55,52.2,'rotated study\nhits vent envelope',fontsize=7,color='#b22266');ax.set_title('Projected Hub C37 body + directional vent restriction',fontsize=10)
ax=axes[1,1];ax.set(xlim=(0,6),ylim=(0,23),xlabel='Z bands only; not an XY footprint',ylabel='height from ATX facing surface / mm');ax.add_patch(Rectangle((.3,0),1,3,facecolor='#70a386',label='ATX low-profile allocation:0..3'))
bottom=gap[0]-c37['height_max_mm'];ax.add_patch(Rectangle((2.1,bottom),1,c37['height_max_mm'],facecolor='#e5a746',alpha=.7,label='Hub C37 body at minimum gap'))
ax.add_patch(Rectangle((2.1,bottom-vent),1,vent,facecolor='#c45c69',alpha=.5,label='C37 directional vent minimum3'))
ax.axhspan(gap[0],gap[1],color='#607ba0',alpha=.25);ax.text(3.4,21.8,'Hub facing plane21.5..22.5',fontsize=8);ax.text(3.4,4.5,'Body bottom4.3 at min gap\nVent band1.3..4.3\nATX top3 overlaps vent1.7',fontsize=8);ax.legend(loc='upper right',fontsize=7);ax.set_title('Why C51 fails: vent requirement, not direct body contact',fontsize=10)
fig.suptitle('SOURCE-BOUND PAIRED OBSTACLE MAP — no new poses, routes or compaction accepted',fontsize=12);fig.savefig(folder/'paired-native-obstacle-map.png',dpi=170)
out=dict(source=str(source.relative_to(ROOT)),source_sha256=sha,peer=str(peer.relative_to(ROOT)),peer_sha256=force._hash(peer),stack_sha256=force._hash(stack),transform=contract['transform'],window_mm=[9,43,26,55],C37_native_model=c37,C37_projected_model=mapping(c37shape),C37_paired_XY_forbidden_for_3mm_low_profile_body_points=mapping(combined_guard),free_point_geometry_excluding_same_face_native_courtyards=mapping(point_free),finite_component_pose_not_certified=True,C37_actual_Z=dict(gap_mm=gap,height_max_mm=c37['height_max_mm'],ATX_low_profile_height_max_mm=height,body_surface_free_at_min_gap_mm=free,vent_min_mm=vent,minimum_vertical_margin_mm=free-vent,body_bottom_at_min_gap_mm=bottom,vent_band_at_min_gap_mm=[bottom-vent,bottom]),native_ATX_courtyards={ref:mapping(courts[ref])for ref in['U6','C54','C55','C51']},moved_U6_plus2_courtyard=mapping(moved_u6),C51_source_body_distance_to_C37_mm=source_distance,C51_rotated_example_courtyard=mapping(example_shape),C51_rotated_example_body_distance_to_C37_mm=distance,C37_nearest_same_face_Hub_obstacles=neighbors[:8],actual_F_copper_inventory=relevant,C37_motion_assessment='A coordinated C37 change can remove this particular vent-XY exclusion in principle, but no pose is selected or certified. It must move its genuine native part/terminals and preserve body/vent, Hub component clearances, native power/ground/cut boundaries, anchors, whole paired body population, and existing C37 vent-reservation copper constraints. Authorization is not inferred from this map.',board_saved=False,new_xy_compaction_mm=[0,0],release_authority=False)
assert force._hash(source)==sha;(folder/'paired-native-obstacle-map.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(source_sha256=sha,Z=out['C37_actual_Z'],source_distance=source_distance,rotated_distance=distance,Hub_nearest=[(q['ref'],q['native_courtyard_distance_mm'])for q in neighbors[:8]],free_point_area_mm2=point_free.area),indent=2))
