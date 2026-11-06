"""One authored RAM-only stronger alternative: Hub external port bank +2X."""
import sys,json
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
import cec_force_current as force,cec_assembly_envelope as assembly
from cec_pipeline import repack
from shapely.geometry import shape,box
from shapely import affinity
from shapely.ops import unary_union
WORK=Path(__file__).parent
CARRIER=ROOT/'experiments/repack/top-output-current-20261106/consumer-pretty-v1/carrier/board.kicad_pcb';COVER=ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb';CONTRACT=ROOT/'beta/assembly/hub-atx-stack.json'
BOUND={CARRIER:'7908e5c235157f5456d5a06a45c3df8c05bbbc30b6cec48629e0f727d8416d3e',COVER:'c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db',CONTRACT:'0ebac5220a5082a85e4ba431ca56152cbc5153a3e0ae67c8eb7d74970188ac1a'}
assert all(force._hash(p)==h for p,h in BOUND.items())
carrier,cover=[pcbnew.LoadBoard(str(p))for p in(CARRIER,COVER)];contract=json.loads(CONTRACT.read_text())
before,populations=assembly.evaluate_boards(carrier,cover,contract)
refine='--refine'in sys.argv;shift=1400000 if refine else 2000000
bank=[r['ref']for r in populations[1]['bodies']if r['height_max_mm']and'xy'in r and shape(r['xy']).bounds[0]==-3.585]
assert bank==['J3','J2','J5','J4']or set(bank)=={'J2','J3','J4','J5'}
fps={f.GetReference():f for f in cover.GetFootprints()};poses=[];incident=[]
for ref in sorted(bank):
 f=fps[ref];old=f.GetPosition();rows=[]
 for p in f.Pads():
  rows.append(dict(uuid=force._uid(p),pin=p.GetNumber(),net=str(p.GetNetname()),source_at_nm=list(p.GetPosition())))
  for t in cover.GetTracks():
   if t.GetNetCode()==p.GetNetCode()and any(t.IsOnLayer(face)and t.GetEffectiveShape(face).Collide(p.GetEffectiveShape(face),0)for face in p.GetLayerSet().CuStack()):
    incident.append(dict(ref=ref,pad_uuid=force._uid(p),track_uuid=force._uid(t),net=str(t.GetNetname()),layer=t.GetLayerName(),width_nm=t.GetWidth()))
 poses.append(dict(reference=ref,uuid=force._uid(f),source_at_nm=list(old),target_at_nm=[old.x+shift,old.y],rotation_deg=f.GetOrientationDegrees(),pads=rows))
 f.Move(pcbnew.VECTOR2I(shift,0))
after,post=assembly.evaluate_boards(carrier,cover,contract)
spec=dict(contract.get('envelopes',{}))
for group in contract.get('envelope_groups',[]):
 for key in group['footprints']:spec[key]=group
planar={key for key,row in spec.items()if row.get('height_max_mm')==0}
same=repack._same_face(cover,set(bank),planar)
support_refs=sorted({r for c in same['conflicts']for r in c['references']}-set(bank))if refine else []
if refine:
 for ref in support_refs:
  f=fps[ref];old=f.GetPosition()
  poses.append(dict(reference=ref,uuid=force._uid(f),source_at_nm=list(old),target_at_nm=[old.x+shift,old.y],rotation_deg=f.GetOrientationDegrees(),small_support_frame=True,pads=[dict(uuid=force._uid(p),pin=p.GetNumber(),net=str(p.GetNetname()),source_at_nm=list(p.GetPosition()))for p in f.Pads()]))
  f.Move(pcbnew.VECTOR2I(shift,0))
 after,post=assembly.evaluate_boards(carrier,cover,contract)
 same=repack._same_face(cover,set(bank)|set(support_refs),planar)
other_fps=[]
for ref in sorted({r for c in same['conflicts']for r in c['references']}-set(bank)):
 f=fps[ref];other_fps.append(dict(reference=ref,uuid=force._uid(f),pose_mm=[v/1e6 for v in f.GetPosition()]+[f.GetOrientationDegrees()],footprint_library=str(f.GetFPID().GetLibNickname()),footprint_name=str(f.GetFPID().GetLibItemName()),pads=[dict(uuid=force._uid(p),pin=p.GetNumber(),net=str(p.GetNetname()))for p in f.Pads()]))
fixed=[shape(post[0]['outline']).intersection(box(2,-1000,1000,1000)),affinity.affine_transform(shape(post[1]['outline']),contract['transform'])]
for idx,pop in enumerate(post):
 for r in pop['bodies']:
  if r['height_max_mm']and'xy'in r:
   g=shape(r['xy']);fixed.append(affinity.affine_transform(g,contract['transform'])if idx else g)
bounds=unary_union(fixed).bounds
# No outline, route, copper or native footprint is saved. The proposed +2
# port/left-edge translation must preserve each mouth's original edge offset.
left_nonbank=[]
for t in cover.GetTracks():
 q=t.GetBoundingBox()
 if q.GetLeft()<3510000:left_nonbank.append(dict(uuid=force._uid(t),net=str(t.GetNetname()),kind=t.GetClass(),left_mm=q.GetLeft()/1e6))
result=dict(schema=1,scope='ONE_MANUAL_RAM_ONLY_PAIRED_ALTERNATIVE_NOT_ROUTED_OR_TRIMMED',authority=[dict(path=str(p),sha256=h)for p,h in BOUND.items()],bank=sorted(bank),support_frame=support_refs,shift_nm=shift,poses=poses,source_incident_native_contacts=incident,before_dimensions=before['projected_dimensions'],port_only_after_dimensions=after['projected_dimensions'],paired_body_check=dict(ok=after['ok'],failed_checks=[r for r in after['checks']if not r['ok']],missing=after['missing'],contacts=after['contacts'],hardware=after['hardware']),same_face=same,additional_overlap_owners=other_fps,with_conditional_carrier_left2mm_trim=dict(bounds_mm=list(bounds),size_mm=[bounds[2]-bounds[0],bounds[3]-bounds[1]],baseline_delta_mm=[89.585-(bounds[2]-bounds[0]),93.09-(bounds[3]-bounds[1])]),source_tracks_vias_near_new_cover_left_edge=left_nonbank,edge_obligation='Translate the receiving Hub left perimeter with the bank to preserve the existing side-entry mouth/edge relation; no new entry direction or accepted future outline is invented. Native all-layer copper, holes and paired screen required after actual construction.',source_files_unchanged=True,source_boards_modified=False,current_qualified=False,gap_changed=False,matched_headers_moved=False,KVM_moved=False,release_authority=False)
assert all(force._hash(p)==h for p,h in BOUND.items())
(WORK/('paired-port-bank-refined.json'if refine else 'paired-port-bank-alternative.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(bank=bank,poses=[{k:v for k,v in p.items()if k!='pads'}for p in poses],paired_ok=after['ok'],paired_failures=[r for r in after['checks']if not r['ok']],same_face=same,overlap_owners=other_fps,port_only=after['projected_dimensions'],conditional=result['with_conditional_carrier_left2mm_trim'],near_left=len(left_nonbank),incident_contacts=len(incident)),indent=2))
