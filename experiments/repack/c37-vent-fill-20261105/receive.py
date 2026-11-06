"""Independent bounded diagnostics; no routing/current/release admission."""
import sys,json,time
from pathlib import Path
from fractions import Fraction
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
import cec_force_current as force,cec_native_fill_geometry as geometry
import cec_assembly_envelope as assembly,cec_native_partition_pair as partition
WORK=Path(__file__).parent
receipt=json.loads((WORK/'correction.json').read_text())
SOURCE=Path(receipt['authority'][0]['path']);TARGET=Path(receipt['candidate']['path'])
assert force._hash(TARGET)==receipt['candidate']['sha256']
assert all(force._hash(Path(v['path']))==v['sha256']for v in receipt['authority'])
mode=sys.argv[1]
if mode=='drc':
 import cec_native_drc_runner as runner
 reports=[]
 for name,path in [('source',SOURCE),('candidate',TARGET)]:
  out=WORK/(name+'-drc.json')
  result=runner.run(path,out,reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',timeout_s=10.,footprint_table=ROOT/'checkpoints/review-20261105-outline-compaction/boards/atx-24pin-rev3/library/fp-lib-table')
  (WORK/(name+'-drc-receipt.json')).write_text(json.dumps(result,indent=2)+'\n')
  d=json.loads(out.read_text());reports.append(d)
  print(name,sum(v['severity']=='error'for v in d['violations']),len(d['unconnected_items']),flush=True)
 identity=lambda d:{json.dumps(v,sort_keys=True)for v in d['violations']if v['severity']=='error'}
 a,b=map(identity,reports)
 result=dict(source_errors=len(a),candidate_errors=len(b),source_opens=len(reports[0]['unconnected_items']),candidate_opens=len(reports[1]['unconnected_items']),new_errors=[json.loads(v)for v in sorted(b-a)])
elif mode=='current':
 import cec_current_debt
 result=cec_current_debt.receive(SOURCE,TARGET,board_hint='atx-24pin-rev3')
 print(json.dumps({k:v for k,v in result.items()if k not in ('before_result','after_result')}),flush=True)
elif mode=='geometry':
 old,new=[pcbnew.LoadBoard(str(p))for p in(SOURCE,TARGET)]
 zones={z.m_Uuid.AsString():z for z in new.Zones()}
 g=zones[receipt['guard_uuid']].Outline();c=zones[receipt['zone_uuid']].GetFilledPolysList(pcbnew.F_Cu)
 rows=lambda p:geometry.snapshot(p,time.monotonic()+10,max_polygons=4096)
 gr,cr=rows(g),rows(c)
 cross=lambda a,b,p:(b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
 def rc(r,p):
  inside=False
  for a,b in zip(r,r[1:]+r[:1]):
   if cross(a,b,p)==0 and min(a[0],b[0])<=p[0]<=max(a[0],b[0])and min(a[1],b[1])<=p[1]<=max(a[1],b[1]):return 0
   if(a[1]>p[1])!=(b[1]>p[1]):
    x=Fraction(a[0])+Fraction(p[1]-a[1])*Fraction(b[0]-a[0],b[1]-a[1])
    if x>p[0]:inside=not inside
  return 1 if inside else -1
 def mc(polys,p):
  for poly in polys:
   o=rc(poly[0],p)
   if o==0:return 0
   if o<0:continue
   hs=[rc(r,p)for r in poly[1:]]
   if 0 in hs:return 0
   if 1 not in hs:return 1
  return -1
 def edges(polys):return [(a,b)for poly in polys for r in poly for a,b in zip(r,r[1:]+r[:1])if a!=b]
 intersections=[];tested=0
 for a,b in edges(gr):
  for u,v in edges(cr):
   if max(a[0],b[0])<min(u[0],v[0])or max(u[0],v[0])<min(a[0],b[0])or max(a[1],b[1])<min(u[1],v[1])or max(u[1],v[1])<min(a[1],b[1]):continue
   tested+=1
   if cross(a,b,u)*cross(a,b,v)<=0 and cross(u,v,a)*cross(u,v,b)<=0:intersections.append([a,b,u,v])
 cg=[p for poly in cr for r in poly for p in r if mc(gr,p)>=0]
 gc=[p for poly in gr for r in poly for p in r if mc(cr,p)>=0]
 assert not intersections and not cg and not gc
 guardgeom=assembly.polygon_from_native(g);coppergeom=assembly.polygon_from_native(c)
 assert guardgeom.is_valid and coppergeom.is_valid and guardgeom.disjoint(coppergeom)
 oldzones={z.m_Uuid.AsString():z for z in old.Zones()}
 oldguard=assembly.polygon_from_native(oldzones[receipt['guard_uuid']].Outline())
 oldcopper=oldzones[receipt['zone_uuid']].GetFilledPolysList(pcbnew.F_Cu)
 original=rows(oldcopper);oe=edges(original)
 exact_old_edges={tuple(map(tuple,e))for e in oe}|{tuple(map(tuple,reversed(e)))for e in oe}
 tested_new_edges=0;outside_spans=[]
 for a,b in edges(cr):
  if tuple(map(tuple,(a,b)))in exact_old_edges:continue
  tested_new_edges+=1;times={Fraction(0),Fraction(1)}
  dx,dy=b[0]-a[0],b[1]-a[1]
  for u,v in oe:
   if max(a[0],b[0])<min(u[0],v[0])or max(u[0],v[0])<min(a[0],b[0])or max(a[1],b[1])<min(u[1],v[1])or max(u[1],v[1])<min(a[1],b[1]):continue
   ex,ey=v[0]-u[0],v[1]-u[1];den=dx*ey-dy*ex
   if den:
    t=Fraction((u[0]-a[0])*ey-(u[1]-a[1])*ex,den)
    s=Fraction((u[0]-a[0])*dy-(u[1]-a[1])*dx,den)
    if 0<=t<=1 and 0<=s<=1:times.add(t)
   else:
    for p in(u,v):
     if cross(a,b,p)==0:
      t=Fraction(p[0]-a[0],dx)if dx else Fraction(p[1]-a[1],dy)
      if 0<=t<=1:times.add(t)
  ts=sorted(times)
  for t0,t1 in zip(ts,ts[1:]):
   t=(t0+t1)/2;p=(Fraction(a[0])+dx*t,Fraction(a[1])+dy*t)
   if mc(original,p)<0:outside_spans.append([a,b,str(t0),str(t1)])
 assert not outside_spans
 sourcegain=coppergeom.difference(assembly.polygon_from_native(oldcopper))
 assert sourcegain.is_empty and guardgeom.covers(oldguard)
 peer=pcbnew.LoadBoard(receipt['authority'][1]['path']);contract=json.loads(Path(receipt['authority'][2]['path']).read_text())
 evaluated,_=assembly.evaluate_boards(new,peer,contract)
 vent=next(v for v in assembly.facing_vents(evaluated,contract,'carrier')if v['ref']=='C37')
 from shapely.geometry import mapping
 screen=assembly.vent_reservations(new,[dict(vent,xy=mapping(guardgeom))]);assert screen[0]['ok']
 result=dict(exact_integer_boundary_intersections=intersections,exact_copper_vertices_inside_or_on_guard=cg,exact_guard_vertices_inside_or_on_copper=gc,integer_bbox_candidate_edge_pairs=tested,exact_saved_polygons_disjoint=True,minimum_shapely_separation_nm=coppergeom.distance(guardgeom)*1e6,new_edges_checked_against_exact_source=tested_new_edges,exact_new_edge_spans_outside_source=outside_spans,independent_source_gain_empty=sourcegain.is_empty,original_guard_wholly_retained=True,strict_full_guard_native_screen=screen,paired_assembly=evaluated,footprint_reservations=assembly.footprint_reservation_check(new))
elif mode=='partition':
 old,new=[pcbnew.LoadBoard(str(p))for p in(SOURCE,TARGET)]
 class NetView:
  def __init__(self,b):self.b=b
  def GetTracks(self):return [t for t in self.b.GetTracks()if t.GetNetname()=='/SENSE5V_HI']
  def GetFootprints(self):return self.b.GetFootprints()
  def Zones(self):return [z for z in self.b.Zones()if z.GetNetname()=='/SENSE5V_HI']
 # Retain every footprint/pad as comparison terminal. Other-net tracks/fills
 # are irrelevant to this authored-net graph; no short is credited as a link.
 proof=partition.compare(NetView(old),NetView(new),timeout_s=10.)
 assert proof['preserved']
 result={k:v for k,v in proof.items()if k not in('source_parts','child_parts','demoted_parts')}
else:raise ValueError(mode)
(WORK/(mode+'-receipt.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result if mode not in('geometry','current')else {k:v for k,v in result.items()if k not in('paired_assembly','before_result','after_result')}),flush=True)
assert force._hash(TARGET)==receipt['candidate']['sha256']
assert all(force._hash(Path(v['path']))==v['sha256']for v in receipt['authority'])
