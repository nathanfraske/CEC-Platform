"""One inventory and one RAM capacitor preview for paired left contraction."""
import sys,json
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
import cec_force_current as force,cec_assembly_envelope as assembly
from cec_pipeline import repack
from shapely.geometry import shape
WORK=Path(__file__).parent
CARRIER=ROOT/'experiments/repack/top-output-current-20261106/consumer-pretty-v1/carrier/board.kicad_pcb';COVER=ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb';CONTRACT=ROOT/'beta/assembly/hub-atx-stack.json'
BOUND={CARRIER:'7908e5c235157f5456d5a06a45c3df8c05bbbc30b6cec48629e0f727d8416d3e',COVER:'c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db',CONTRACT:'0ebac5220a5082a85e4ba431ca56152cbc5153a3e0ae67c8eb7d74970188ac1a'}
assert all(force._hash(p)==h for p,h in BOUND.items())
carrier,cover=[pcbnew.LoadBoard(str(p))for p in(CARRIER,COVER)];contract=json.loads(CONTRACT.read_text())
before,pops=assembly.evaluate_boards(carrier,cover,contract)
def bounds(q):return[q.GetLeft()/1e6,q.GetTop()/1e6,q.GetRight()/1e6,q.GetBottom()/1e6]
inventory={}
for side,b,threshold in [('cover',cover,81),('carrier',carrier,4.5)]:
 rows=[];courts=[];holes=[]
 def near(r):return r[2]>threshold if side=='cover'else r[0]<threshold
 for f in b.GetFootprints():
  native=f.GetCourtyard(f.GetLayer())
  if native.OutlineCount():
   r=list(assembly.polygon_from_native(native).bounds)
   if near(r):courts.append(dict(ref=f.GetReference(),uuid=force._uid(f),pose_mm=[v/1e6 for v in f.GetPosition()]+[f.GetOrientationDegrees()],bounds_mm=r))
  for p in f.Pads():
   r=bounds(p.GetBoundingBox())
   if near(r):rows.append(dict(kind='PAD',ref=f.GetReference(),pin=p.GetNumber(),uuid=force._uid(p),net=str(p.GetNetname()),bounds_mm=r,at_mm=[v/1e6 for v in p.GetPosition()],drill_mm=[v/1e6 for v in p.GetDrillSize()]))
   if p.HasHole():
    pos=p.GetPosition();drill=p.GetDrillSize();r=[(pos.x-drill.x/2)/1e6,(pos.y-drill.y/2)/1e6,(pos.x+drill.x/2)/1e6,(pos.y+drill.y/2)/1e6]
    if near(r):holes.append(dict(ref=f.GetReference(),pin=p.GetNumber(),uuid=force._uid(p),bounds_mm=r))
 for t in b.GetTracks():
  r=bounds(t.GetBoundingBox())
  if near(r):rows.append(dict(kind=t.GetClass(),uuid=force._uid(t),net=str(t.GetNetname()),bounds_mm=r,start_mm=[v/1e6 for v in t.GetStart()],end_mm=[v/1e6 for v in t.GetEnd()],width_mm=t.GetWidth()/1e6))
 inventory[side]=dict(threshold_mm=threshold,courtyards=sorted(courts,key=lambda r:r['bounds_mm'][2],reverse=True)if side=='cover'else sorted(courts,key=lambda r:r['bounds_mm'][0]),material=sorted(rows,key=lambda r:r['bounds_mm'][2],reverse=True)if side=='cover'else sorted(rows,key=lambda r:r['bounds_mm'][0]),holes=holes)
source_c1=cover.FindFootprintByReference('C1');old=source_c1.GetPosition();source_c1.Move(pcbnew.VECTOR2I(-1000000,0))
after,post=assembly.evaluate_boards(carrier,cover,contract)
spec=dict(contract.get('envelopes',{}))
for g in contract.get('envelope_groups',[]):
 for k in g['footprints']:spec[k]=g
planar={k for k,r in spec.items()if r.get('height_max_mm')==0}
same=repack._same_face(cover,{'C1'},planar)
vents=assembly.vent_reservations(carrier,assembly.facing_vents(after,contract,'carrier'))
result=dict(schema=1,scope='ONE_READ_ONLY_INVENTORY_AND_ONE_C1_RAM_PREVIEW_NOT_ROUTE_OR_OUTLINE_ADMISSION',authority=[dict(path=str(p),sha256=h)for p,h in BOUND.items()],inventory=inventory,source_dimensions=before['projected_dimensions'],C1_pose=dict(uuid=force._uid(source_c1),source_at_nm=list(old),target_at_nm=[old.x-1000000,old.y],rotation_deg=source_c1.GetOrientationDegrees()),C1_minus1mm_preview=dict(paired_body_ok=after['ok'],paired_failures=[r for r in after['checks']if not r['ok']],same_face=same,existing_vent_reservations=vents,new_C1_declared_body_bounds_mm=list(shape(next(r for r in post[1]['bodies']if r['ref']=='C1')['xy']).bounds)),source_files_unchanged=True,interfaces_moved=False,gap_changed=False,KVM_moved=False,qualified_current_or_Z_or_release=False)
assert all(force._hash(p)==h for p,h in BOUND.items())
(WORK/'paired-left-contraction-inventory.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(courts={s:v['courtyards']for s,v in inventory.items()},extreme_material={s:v['material'][:12]for s,v in inventory.items()},holes={s:v['holes']for s,v in inventory.items()},preview=result['C1_minus1mm_preview']),indent=2))
