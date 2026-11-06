"""Bounded private, selected-zone refill experiment. Never source admission."""
import copy,json,sys,time
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
import cec_force_current as force,cec_additive_route_receiving as syntax
import cec_field_coupling as field,cec_zone_fill as fill
import cec_assembly_envelope as assembly,cec_native_fill_geometry as geometry
from fractions import Fraction
SOURCE=ROOT/'experiments/repack/atx-small-cell-20261105/native-v5/carrier/board.kicad_pcb'
PEER=ROOT/'experiments/repack/hub-kvm-20261105/native-v15/cover/board.kicad_pcb'
CONTRACT=ROOT/'beta/assembly/hub-atx-stack.json'
WORK=Path(__file__).parent
BOUNDS={SOURCE:'dcc749c6d75bac04675ec7260f8709ee78ff798fd6d18a618f9819c56cdd7688',PEER:'c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db',CONTRACT:'0ebac5220a5082a85e4ba431ca56152cbc5153a3e0ae67c8eb7d74970188ac1a'}
GUARD='cdb78967-3235-44b9-962b-6ce7aa574142';ZONE='4298863e-593a-4614-93d4-b005e5fa434e'
assert all(force._hash(p)==h for p,h in BOUNDS.items())
board=pcbnew.LoadBoard(str(SOURCE));old=pcbnew.LoadBoard(str(SOURCE))
guard=next(z for z in board.Zones()if z.m_Uuid.AsString()==GUARD)
zone=next(z for z in board.Zones()if z.m_Uuid.AsString()==ZONE)
assert zone.GetNetname()=='/SENSE5V_HI' and not zone.GetIsRuleArea()
prior=pcbnew.LoadBoard(str(ROOT/'experiments/repack/c37-vent-refresh-20261105/candidate/carrier/board.kicad_pcb'))
union=next(z for z in prior.Zones()if z.m_Uuid.AsString()==GUARD).Outline()
guard.Outline().RemoveAllContours();guard.Outline().Append(union)
before=zone.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
result=dict(authority=[dict(path=str(p),sha256=h)for p,h in BOUNDS.items()],guard_uuid=GUARD,zone_uuid=ZONE,net=str(zone.GetNetname()),status='PRIVATE_PROBE_NOT_ADMITTED')
if '--correct' in sys.argv:
 # Exact source-owned saved fill, minus one conservative native 10 nm halo.
 # This is a construction operation, never a collision tolerance or waiver.
 cutter=guard.Outline().CloneDropTriangulation()
 cutter.Inflate(10,pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,1)
 corrected=before.CloneDropTriangulation();corrected.BooleanSubtract(cutter)
 # Native Boolean clipping rounds new crossings to integer nm. Correct only
 # generated vertices that lie outside the exact source; never move an old
 # vertex or round toward foreign copper. This is independently checked below.
 def rings(p):return geometry.snapshot(p,time.monotonic()+10,max_polygons=4096)
 original=rings(before);cutrows=rings(cutter)
 def cross(a,b,p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
 def ringclass(r,p):
  inside=False
  for a,b in zip(r,r[1:]+r[:1]):
   if cross(a,b,p)==0 and min(a[0],b[0])<=p[0]<=max(a[0],b[0])and min(a[1],b[1])<=p[1]<=max(a[1],b[1]):return 0
   if (a[1]>p[1])!=(b[1]>p[1]):
    x=Fraction(a[0])+Fraction(p[1]-a[1])*Fraction(b[0]-a[0],b[1]-a[1])
    if x>p[0]:inside=not inside
  return 1 if inside else -1
 def material(rows,p):
  for poly in rows:
   outer=ringclass(poly[0],p)
   if outer==0:return 0
   if outer<0:continue
   hs=[ringclass(r,p)for r in poly[1:]]
   if 0 in hs:return 0
   if 1 not in hs:return 1
  return -1
 rows=rings(corrected);adjustments=[]
 oldpoints={tuple(p)for poly in original for r in poly for p in r}
 for poly in rows:
  for ring in poly:
   for index,p in enumerate(ring):
    if material(original,p)>=0:continue
    assert tuple(p)not in oldpoints
    options=sorted(([p[0]+dx,p[1]+dy]for dx in(-1,0,1)for dy in(-1,0,1)if dx or dy),key=lambda q:((q[0]-p[0])**2+(q[1]-p[1])**2,q))
    q=next(q for q in options if material(original,q)==1 and material(cutrows,q)==-1)
    adjustments.append(dict(from_nm=p,to_nm=q));ring[index]=q
 corrected=geometry.reconstruct(rows,time.monotonic()+10,max_polygons=4096)
 corrected.Fracture();zone.UnFill()
 zone.SetFilledPolysList(pcbnew.F_Cu,corrected);zone.SetIsFilled(True)
 result['construction']=dict(operation='source_saved_fill_minus_native_guard_10nm_halo',halo_nm=10,native_curve_error_nm=1,no_global_refill=True,conservative_integer_rounding=adjustments)
else:
 result['compile']=fill.compile_selected(board,[zone],timeout_s=10.,initialize_selected=True)
after=zone.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
def summary(p):
 return dict(area_mm2=p.Area()/1e12,polygons=p.OutlineCount(),rings=geometry.snapshot(p,time.monotonic()+10,max_polygons=4096)if p.OutlineCount()else [])
lost=before.CloneDropTriangulation();lost.BooleanSubtract(after)
gain=after.CloneDropTriangulation();gain.BooleanSubtract(before)
overlap=after.CloneDropTriangulation();overlap.BooleanIntersection(guard.Outline())
result.update(loss=summary(lost),gain=summary(gain),guard_overlap=summary(overlap))
# Save only private diagnostic refill before deciding if it is local enough.
raw=WORK/'raw-native.kicad_pcb';field._save_field_snapshot(board,raw)
root,nodes=syntax._nodes(SOURCE);_,fresh=syntax._nodes(raw)
for uid,tags in [(GUARD,{'polygon'}),(ZONE,{'filled_polygon','filled_areas_thickness'})]:
 original=nodes[uid];replacement=copy.deepcopy(original)
 replacement[:]=[n for n in replacement if not(isinstance(n,list)and n and n[0]in tags)]
 replacement.extend(copy.deepcopy(n)for n in fresh[uid]if isinstance(n,list)and n and n[0]in tags)
 root[1:]=[replacement if n is original else n for n in root[1:]]
directory='corrected-rounded/carrier'if '--correct'in sys.argv else 'candidate/carrier'
target=force._copy_family(SOURCE,WORK/directory);target.write_text(syntax._render(root)+'\n')
_,final=syntax._nodes(target)
strip=lambda n,tags:[v for v in n if not(isinstance(v,list)and v and v[0]in tags)]
assert all(final[k]==v for k,v in nodes.items()if k not in {GUARD,ZONE})
assert strip(final[GUARD],{'polygon'})==strip(nodes[GUARD],{'polygon'})
assert strip(final[ZONE],{'filled_polygon','filled_areas_thickness'})==strip(nodes[ZONE],{'filled_polygon','filled_areas_thickness'})
result['candidate']=dict(path=str(target),sha256=force._hash(target))
result['only_guard_polygon_and_selected_saved_fill_changed']=True
result['source_hashes_preserved']=all(force._hash(p)==h for p,h in BOUNDS.items())
(WORK/('correction.json'if '--correct'in sys.argv else 'probe.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items()if k not in ('loss','gain','guard_overlap')}))
print(json.dumps({k:{a:b for a,b in result[k].items()if a!='rings'}for k in ('loss','gain','guard_overlap')}))
