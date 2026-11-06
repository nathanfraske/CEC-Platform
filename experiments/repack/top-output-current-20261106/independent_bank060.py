"""Read-only exact-byte independent field/vent/assembly verification."""
import sys,json,time,argparse
from pathlib import Path
from fractions import Fraction
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
import cec_force_current as force,cec_field_coupling as field
import cec_assembly_envelope as assembly,cec_native_fill_geometry as geometry
from cec_stack_fit_screen import vertical_screen
from shapely.geometry import mapping
parser=argparse.ArgumentParser()
parser.add_argument('mode',choices=('fields','mechanical'))
parser.add_argument('--candidate-directory',default='experiments/repack/top-output-current-20261106/consumer-clearance-bank060-v1')
parser.add_argument('--candidate-sha256',default='1fba73346bbe8a9a6c29d9b8c00c148b9685fc12b5b925174071495efddc51a3')
args=parser.parse_args()
BASE=ROOT/args.candidate_directory
SOURCE=ROOT/'experiments/repack/paired-closed-v2-20261105/carrier/board.kicad_pcb'
TARGET=BASE/'carrier/board.kicad_pcb'
PEER=ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb'
CONTRACT=ROOT/'beta/assembly/hub-atx-stack.json'
BOUND={SOURCE:'b52754d95fad20386528c9b5cd9abdc44c6697032baff1d7ebaeded2f95ab8f1',TARGET:args.candidate_sha256,PEER:'c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db',CONTRACT:'0ebac5220a5082a85e4ba431ca56152cbc5153a3e0ae67c8eb7d74970188ac1a'}
assert all(force._hash(p)==h for p,h in BOUND.items())
mode=args.mode;result=dict(authority=[dict(path=str(p),sha256=h)for p,h in BOUND.items()],scope='PRIVATE_READ_ONLY_INDEPENDENT_CHECK_NOT_RELEASE',mode=mode)
if mode=='fields':
 reports=[]
 for label,path in(('before',SOURCE),('after',TARGET)):
  report=field.field_coupling_summary(str(path),board_hint='atx-24pin-rev3')
  out=BASE/('independent-fields-'+label+'.json');out.write_text(json.dumps(report,indent=2)+'\n')
  reports.append(report)
 keys=[field.blocker_keys(r)for r in reports]
 result.update(before_ok=reports[0]['ok'],after_ok=reports[1]['ok'],before_blockers=len(keys[0]),after_blockers=len(keys[1]),new_blockers=sorted(keys[1]-keys[0]),removed_blockers=sorted(keys[0]-keys[1]),report_paths=[str(BASE/('independent-fields-'+label+'.json'))for label in('before','after')])
else:
 old,new,peer=[pcbnew.LoadBoard(str(p))for p in(SOURCE,TARGET,PEER)]
 contract=json.loads(CONTRACT.read_text());evaluated,data=assembly.evaluate_boards(new,peer,contract)
 evaluated['vertical']=vertical_screen(**contract['vertical']);evaluated['ok'] &= evaluated['vertical']['ok']
 evaluated['vent_reservations']=[]
 for receiver,board in(('carrier',new),('cover',peer)):
  evaluated['vent_reservations'].extend(dict(r,receiver=receiver)for r in assembly.vent_reservations(board,assembly.facing_vents(evaluated,contract,receiver)))
 evaluated['ok'] &= all(r['ok']for r in evaluated['vent_reservations'])
 outlines=[]
 for b in(old,new):
  p=pcbnew.SHAPE_POLY_SET();assert b.GetBoardPolygonOutlines(p,False)
  outlines.append(geometry.snapshot(p,time.monotonic()+10,max_polygons=4096))
 assert outlines[0]==outlines[1]
 guard=next(z for z in new.Zones()if z.m_Uuid.AsString()=='cdb78967-3235-44b9-962b-6ce7aa574142')
 gp=guard.Outline();g=assembly.polygon_from_native(gp)
 def snap(p):return geometry.snapshot(p,time.monotonic()+10,max_polygons=4096)
 def edges(rows):return [(a,b)for poly in rows for r in poly for a,b in zip(r,r[1:]+r[:1])if a!=b]
 def cross(a,b,p):return(b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
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
 gr=snap(gp);ge=edges(gr);checks=[]
 for z in new.Zones():
  if z.GetIsRuleArea()or not z.GetLayerSet().Contains(pcbnew.F_Cu)or not z.IsFilled():continue
  p=z.GetFilledPolysList(pcbnew.F_Cu)
  if not p.OutlineCount():continue
  q=p.CloneDropTriangulation();q.BooleanIntersection(gp)
  assert not q.OutlineCount()
  if not p.BBox().Intersects(gp.BBox()):
   checks.append(dict(uuid=z.m_Uuid.AsString(),net=str(z.GetNetname()),exact_disjoint_basis='integer_bounding_boxes'));continue
  cr=snap(p);hits=[]
  for a,b in ge:
   for u,v in edges(cr):
    if max(a[0],b[0])<min(u[0],v[0])or max(u[0],v[0])<min(a[0],b[0])or max(a[1],b[1])<min(u[1],v[1])or max(u[1],v[1])<min(a[1],b[1]):continue
    if cross(a,b,u)*cross(a,b,v)<=0 and cross(u,v,a)*cross(u,v,b)<=0:hits.append([a,b,u,v])
  cv=[p for poly in cr for r in poly for p in r if mc(gr,p)>=0]
  gv=[p for poly in gr for r in poly for p in r if mc(cr,p)>=0]
  assert not hits and not cv and not gv
  checks.append(dict(uuid=z.m_Uuid.AsString(),net=str(z.GetNetname()),exact_disjoint_basis='integer_edge_intersections_and_rational_winding',boundary_intersections=0,copper_vertices_in_or_on_guard=0,guard_vertices_in_or_on_copper=0))
 result.update(outline_exact_unchanged=True,carrier_outline_bounds_mm=list(assembly.polygon_from_native(geometry.reconstruct(outlines[1],time.monotonic()+10,max_polygons=4096)).bounds),full_c37_guard_all_filled_copper_exact_disjoint=True,filled_zone_checks=checks,paired_native_assembly=evaluated,footprint_reservations=assembly.footprint_reservation_check(new))
assert all(force._hash(p)==h for p,h in BOUND.items())
result.update(authority_unchanged=True,current_or_thermal_qualified=False,release_authority=False)
out=BASE/('independent-'+mode+'.json');out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items()if k not in('filled_zone_checks','paired_native_assembly','authority')},indent=2))
print(str(out))
