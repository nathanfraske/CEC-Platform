"""Actual saved native fill diff and conservative planar erosion, not ampacity admission."""
import sys,json,time,math
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_assembly_envelope as assembly
from shapely.geometry import mapping,LineString
from shapely.ops import unary_union
p,_=_native();folder=Path(__file__).parent
source=ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb'
candidate=folder/'hub-C37-vent-v1/candidate/board.kicad_pcb';uid='fc65fef1-239d-4859-94dd-f827621e549e'
assert force._hash(source)=='c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db'
assert force._hash(candidate)=='4825def1abce879355b751406634f2dc5d552c207c779710b3cd6877ecf05992'
a=p.LoadBoard(str(source));b=p.LoadBoard(str(candidate))
za=next(z for z in a.Zones()if force._uid(z)==uid);zb=next(z for z in b.Zones()if force._uid(z)==uid)
sa=assembly.polygon_from_native(za.GetFilledPolysList(p.F_Cu));sb=assembly.polygon_from_native(zb.GetFilledPolysList(p.F_Cu))
removed=sa.difference(sb);added=sb.difference(sa);changed=removed.union(added)
def info(g,with_geometry=False):
 d=dict(area_mm2=g.area,bounds_mm=list(g.bounds),type=g.geom_type,components=len(getattr(g,'geoms',[g])))
 if with_geometry:d['geometry']=mapping(g)
 return d
out=dict(source=str(source.relative_to(ROOT)),source_sha256=force._hash(source),candidate=str(candidate.relative_to(ROOT)),candidate_sha256=force._hash(candidate),
 zone_uuid=uid,net=za.GetNetname(),layer='F.Cu',source_fill=info(sa),candidate_fill=info(sb),removed=info(removed,True),added=info(added,True),width_floor_mm=1.,
 native_zone_local_clearance_nm=za.GetLocalClearance())
rows=[]
for label,board,zonefill in [('source',a,sa),('candidate',b,sb)]:
 pieces=[assembly.polygon_from_native(z.GetFilledPolysList(p.F_Cu))for z in board.Zones()if not z.GetIsRuleArea()and z.GetNetname()==za.GetNetname()and z.HasFilledPolysForLayer(p.F_Cu)]
 for t in board.GetTracks():
  if t.GetNetname()!=za.GetNetname()or not t.IsOnLayer(p.F_Cu):continue
  poly=p.SHAPE_POLY_SET();t.TransformShapeToPolygon(poly,p.F_Cu,0,1000,p.ERROR_INSIDE);pieces.append(assembly.polygon_from_native(poly))
 pads=[q for fp in board.GetFootprints()for q in fp.Pads()if q.GetNetname()==za.GetNetname()and q.IsOnLayer(p.F_Cu)]
 pieces.extend(assembly.polygon_from_native(q.GetEffectivePolygon(p.F_Cu))for q in pads)
 copper=unary_union(pieces)
 # Drill voids are never copper capacity. Native exact hole polygons, conservative outside error.
 holes=[]
 for obj in [*board.GetTracks(),*(q for fp in board.GetFootprints()for q in fp.Pads())]:
  if not obj.IsOnLayer(p.F_Cu):continue
  if obj.GetClass()=='PCB_VIA':
   from shapely.geometry import Point
   holes.append(Point(obj.GetPosition().x/1e6,obj.GetPosition().y/1e6).buffer(obj.GetDrillValue()/2e6,resolution=128))
  elif obj.GetClass()=='PAD'and obj.HasHole():
   poly=p.SHAPE_POLY_SET();obj.TransformHoleToPolygon(poly,0,1000,p.ERROR_OUTSIDE);holes.append(assembly.polygon_from_native(poly))
 if holes:copper=copper.difference(unary_union(holes))
 # Inflate the erosion radius to cover round-segment sagitta, plus 1 nm.
 erosion_radius=.5/math.cos(math.pi/(4*128))+.000001
 erosion=copper.buffer(-erosion_radius,join_style='round',resolution=128)
 components=list(getattr(erosion,'geoms',[erosion]));terminals=[];near=[]
 for fp in board.GetFootprints():
  for q in fp.Pads():
   if not q.IsOnLayer(p.F_Cu):continue
   land=assembly.polygon_from_native(q.GetEffectivePolygon(p.F_Cu))
   record=dict(ref=fp.GetReference(),pin=q.GetNumber(),uuid=force._uid(q),net=q.GetNetname(),center_mm=[q.GetPosition().x/1e6,q.GetPosition().y/1e6],land=info(land),distance_to_change_mm=land.distance(changed))
   if land.distance(changed)<2.:near.append(record)
   if q.GetNetname()==za.GetNetname():
    record.update(actual_land_copper_contact_area_mm2=land.intersection(copper).area,
     eroded_component_indices=[i for i,g in enumerate(components)if land.intersects(g)],
     endpoint_support='Literal native pad intersects the eroded copper component; no expanded/artificial terminal bridge')
    terminals.append(record)
 rows.append(dict(label=label,erosion_radius_mm=erosion_radius,zone_only_eroded=info(zonefill.buffer(-erosion_radius,resolution=128)),
  all_same_net_FCu_actual_union=info(copper),all_same_net_FCu_eroded=info(erosion),
  eroded_components=[dict(index=i,**info(g))for i,g in enumerate(components)],terminals=terminals,all_net_pads_near_change=near,
  changed_region_distance_to_surviving_erosion_mm=changed.distance(erosion),
  zone_horizontal_sections=[dict(y_mm=y,geometry=mapping(zonefill.intersection(LineString([(74.,y),(76.,y)]))),
    total_copper_width_mm=zonefill.intersection(LineString([(74.,y),(76.,y)])).length)for y in (38.4,38.6,42.65,46.7,46.9)]))
out.update(states=rows,geometric_only=True,no_barrel_capacity_credit=True,no_new_authority=True,board_saved=False,release_authority=False,
 limitations='Conservative same-face inscribed 1 mm disk corridor. Round-buffer polygon approximation explicitly recorded; failure is not proof that actual current capacity is insufficient. Whole-board cross-face/thermal/current admission remains separate.')
(folder/'Hub-C37-fill-native-geometry.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(dict(removed=out['removed'],added=out['added'],states=[dict(label=r['label'],eroded=r['all_same_net_FCu_eroded'],terminals=[(t['ref'],t['pin'],t['eroded_component_indices'])for t in r['terminals']],near=[(t['ref'],t['pin'],t['net'],t['distance_to_change_mm'])for t in r['all_net_pads_near_change']])for r in rows]),default=str)[:7000])
