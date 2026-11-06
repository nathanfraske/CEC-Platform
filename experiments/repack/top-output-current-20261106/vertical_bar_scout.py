"""Three explicitly chosen native nominal bridge rejection screens; no edits."""
import sys,json,time
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
import cec_force_current as force,cec_assembly_envelope as assembly
from cec_pipeline import bridges
from shapely.geometry import shape,mapping,LineString
from shapely import affinity
SOURCE=ROOT/'experiments/repack/top-output-current-20261106/consumer-clearance-bank060-v1/carrier/board.kicad_pcb'
PEER=ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb'
CONTRACT=ROOT/'beta/assembly/hub-atx-stack.json'
BOUND={SOURCE:'1fba73346bbe8a9a6c29d9b8c00c148b9685fc12b5b925174071495efddc51a3',PEER:'c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db',CONTRACT:'0ebac5220a5082a85e4ba431ca56152cbc5153a3e0ae67c8eb7d74970188ac1a'}
assert all(force._hash(p)==h for p,h in BOUND.items())
b=pcbnew.LoadBoard(str(SOURCE));peer=pcbnew.LoadBoard(str(PEER));contract=json.loads(CONTRACT.read_text())
part=json.loads((ROOT/'experiments/busbars/mac8-mjp-1.0-nominal.json').read_text())
evaluated,populations=assembly.evaluate_boards(b,peer,contract)
fps={f.GetReference():f for f in b.GetFootprints()};candidates=[]
for x,y in[(24.5,40.5),(26,41),(27,41.5),(30.6,41.5)]:
 candidate=dict(id=f'vertical-{x}-{y}',face='F.Cu',ends_nm=[[round(x*1e6),round(y*1e6)],[round(x*1e6),round((y+25.4)*1e6)]])
 result,data=bridges.screen_native(b,part,candidate,net='/SENSE12V_HI',clearance=lambda other:200000,mechanical_margin_nm=250000,deadline=time.monotonic()+8)
 body,lands=bridges.placed_shapes(part,candidate);peerhits=[]
 for row in populations[1]['bodies']:
  if not row.get('inward')or not row['height_max_mm']or 'xy'not in row:continue
  g=affinity.affine_transform(shape(row['xy']),contract['transform'])
  if body.buffer(.15+.15+.5,join_style='mitre').intersects(g):
   margin=contract['gap_mm'][0]-part['height_nm']/1e6-row['height_max_mm']-contract['body_clearance_mm']
   peerhits.append(dict(ref=row['ref'],height_max_mm=row['height_max_mm'],nominal_vertical_margin_mm=margin,nominal_reject=margin<0,overlap_mm2=body.intersection(g).area))
 # Give every same-face owner its real pose and incident source widths/nets.
 owners=[]
 for row in result['same_face_body_reservations']:
  f=fps[row['reference']];padrows=[]
  for p in f.Pads():
   padrows.append(dict(pin=p.GetNumber(),uuid=p.m_Uuid.AsString(),net=str(p.GetNetname()),at_mm=[v/1e6 for v in p.GetPosition()]))
  owners.append(dict(**row,footprint_uuid=f.m_Uuid.AsString(),pose_mm=[v/1e6 for v in f.GetPosition()]+[f.GetOrientationDegrees()],pads=padrows))
 result.update(body_xy=mapping(body),lands_xy=[mapping(p)for p in lands],same_face_owners=owners,opposing_body_checks=peerhits,nominal_opposing_body_rejects=[v for v in peerhits if v['nominal_reject']],clearance_basis='Explicit0.2mm nominal rejection assumption only; NOT custom-rule clearance acceptance',stub_endpoints_mm=dict(upper=[[18.6,36],[x,y]],lower=[[x,y+25.4],[18.349999,77.4]]),stub_copper_not_constructed_or_received=True)
 candidates.append(result)
def bbox(item):
 r=item.GetBoundingBox();return [r.GetLeft()/1e6,r.GetTop()/1e6,r.GetRight()/1e6,r.GetBottom()/1e6]
other=[]
for t in b.GetTracks():
 if t.GetNetname()not in('GND','/SENSE12V_HI'):other.append(dict(uuid=t.m_Uuid.AsString(),net=str(t.GetNetname()),kind=t.GetClass(),bounds_mm=bbox(t)))
for f in b.GetFootprints():
 for p in f.Pads():
  if p.GetNetname()not in('GND','/SENSE12V_HI'):other.append(dict(uuid=p.m_Uuid.AsString(),ref=f.GetReference(),pin=p.GetNumber(),net=str(p.GetNetname()),kind='PAD',bounds_mm=bbox(p)))
for z in b.Zones():
 if not z.GetIsRuleArea()and z.GetNetname()not in('GND','/SENSE12V_HI')and z.IsFilled():
  for face in z.GetLayerSet().CuStack():
   p=z.GetFilledPolysList(face)
   if p.OutlineCount():other.append(dict(uuid=z.m_Uuid.AsString(),net=str(z.GetNetname()),kind='FILLED_ZONE',layer=pcbnew.LayerName(face),bounds_mm=list(assembly.polygon_from_native(p).bounds)))
result=dict(schema=1,authority=[dict(path=str(p),sha256=h)for p,h in BOUND.items()],candidates=candidates,leftmost_non12v_nonground_material=sorted(other,key=lambda r:r['bounds_mm'][0])[:20],projected_dimensions_before=evaluated['projected_dimensions'],not_current_or_assembly_or_release_qualified=True,board_mutated=False)
assert all(force._hash(p)==h for p,h in BOUND.items())
out=ROOT/'docs/evidence/20261105-bottom-compaction/vertical-mjp-native-scout.json';out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(candidates=[dict(id=r['id'],owners=[v['reference']for v in r['same_face_owners']],land_conflicts=r['land_conflicts'],holes=r['nearby_holes_or_leads'],unknown=r['unknown'],opposing=r['opposing_body_checks'])for r in candidates],other_left=sorted(other,key=lambda r:r['bounds_mm'][0])[:8]),indent=2))
