import sys,json,math
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_assembly_envelope as assembly
import cec_fab_profile as fab
from shapely.affinity import translate
p,_=_native();source=ROOT/'experiments/busbars/coherent-mux-20261106/port-repaired-v1/candidate/board.kicad_pcb';b=p.LoadBoard(str(source));sha=force._hash(source);fps={f.GetReference():f for f in b.GetFootprints()};moves={r:(2,0)for r in ['U6','C9','C27','C54','R54']};moves['C55']=(1.8,0);pads=[q for fp in b.GetFootprints()for q in fp.Pads()];tracks=list(b.GetTracks());layers=list(b.GetEnabledLayers().CuStack())
simple='--simple'in sys.argv
assert sha=='d4cf0b22f92526b6bdca0ae7cfa09af02217647db984577064ce91bfc177958a'
if simple:moves={r:(1,0)for r in ['U6','C9','C27','R54']}
def item(t):
 return dict(uuid=force._uid(t),kind=t.GetClass(),net=t.GetNetname(),layer=t.GetLayerName(),start_nm=list(t.GetStart()),end_nm=list(t.GetEnd()),locked=t.IsLocked(),width_nm=t.GetWidth()if t.GetClass()=='PCB_TRACK'else t.GetWidth(t.TopLayer()))
contacts=[]
for q in fps['C55'].Pads():
 rows=[]
 for t in tracks:
  if any(q.IsOnLayer(l)and t.IsOnLayer(l)and q.GetEffectiveShape(l).Collide(t.GetEffectiveShape(l),0)for l in layers):rows.append(item(t))
 zones=[]
 for z in b.Zones():
  if z.GetIsRuleArea():continue
  for l in layers:
   if not q.IsOnLayer(l)or not z.IsOnLayer(l):continue
   if z.IsFilled()and z.HasFilledPolysForLayer(l)and z.GetFilledPolysList(l).Collide(q.GetEffectiveShape(l),0):zones.append(dict(uuid=force._uid(z),net=z.GetNetname(),layer=b.GetLayerName(l)))
 branch_neighbors=[]
 for row in rows:
  t=next(t for t in tracks if force._uid(t)==row['uuid'])
  for other in tracks:
   if force._uid(other)==force._uid(t):continue
   if any(t.IsOnLayer(l)and other.IsOnLayer(l)and t.GetEffectiveShape(l).Collide(other.GetEffectiveShape(l),0)for l in layers):branch_neighbors.append(dict(branch_uuid=force._uid(t),neighbor=item(other)))
  for pad in pads:
   if any(t.IsOnLayer(l)and pad.IsOnLayer(l)and t.GetEffectiveShape(l).Collide(pad.GetEffectiveShape(l),0)for l in layers):branch_neighbors.append(dict(branch_uuid=force._uid(t),pad_owner=pad.GetParentFootprint().GetReference(),pad=pad.GetNumber(),pad_uuid=force._uid(pad),net=pad.GetNetname()))
 contacts.append(dict(pad=q.GetNumber(),net=q.GetNetname(),pad_uuid=force._uid(q),native_copper_contacts=rows,native_filled_zone_contacts=zones,branch_native_neighbors=branch_neighbors))
barrels=[]
for v in tracks:
 if v.GetClass()!='PCB_VIA':continue
 if not any(math.dist(tuple(q.GetPosition()),tuple(v.GetPosition()))<=2000000 for ref in moves for q in fps[ref].Pads()):continue
 owners=[]
 for q in pads:
  if q.GetAttribute()!=p.PAD_ATTRIB_SMD or q.GetNetCode()!=v.GetNetCode():continue
  if math.dist(tuple(q.GetPosition()),tuple(v.GetPosition()))>2000000:continue
  face=list(q.GetLayerSet().CuStack())
  if len(face)!=1:continue
  lid=face[0];at=v.GetPosition();poly=p.SHAPE_POLY_SET();v.TransformShapeToPolygon(poly,lid,0,1,p.ERROR_OUTSIDE);poly.BooleanSubtract(q.GetEffectivePolygon(lid,p.ERROR_INSIDE))
  basis='contained'if poly.OutlineCount()==0 else None
  tails=[]
  if not basis:
   for t in tracks:
    if t.GetClass()!='PCB_TRACK'or t.GetNetCode()!=v.GetNetCode()or t.GetLayer()!=lid:continue
    if any(math.dist(tuple(z),tuple(at))<=5000 for z in(t.GetStart(),t.GetEnd()))and(fab.local_pofv_dogbone_matches(q,t.GetStart(),t.GetEnd(),lid,v.GetNetCode())or fab.local_pofv_dogbone_matches(q,t.GetEnd(),t.GetStart(),lid,v.GetNetCode())):tails.append(force._uid(t))
   if tails:basis='native_short_dogbone'
  if basis:owners.append(dict(ref=q.GetParentFootprint().GetReference(),pad=q.GetNumber(),basis=basis,tails=tails))
 active=[o for o in owners if o['ref']in moves]
 if active:barrels.append(dict(source=item(v),owners=owners,active=active,process=fab.local_pofv_via_decision(b,v),unique_rigid_delta=len({moves[o['ref']]for o in active})==1))
shapes={}
for ref,fp in fps.items():
 try:shapes[ref]=assembly.footprint_planar_envelope(fp)[0]
 except ValueError:pass
collisions=[]
for ref,delta in moves.items():
 shape=translate(shapes[ref],*delta)
 for other,poly in shapes.items():
  if other==ref or fps[other].GetLayer()!=fps[ref].GetLayer():continue
  poly=translate(poly,*moves.get(other,(0,0)))
  if shape.intersects(poly):collisions.append(dict(refs=[ref,other],intersection_area_mm2=shape.intersection(poly).area,bounds=[list(shape.bounds),list(poly.bounds)]))
peer=p.LoadBoard(str(ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb'));contract=json.loads((ROOT/'beta/assembly/hub-atx-stack.json').read_text());paired=assembly.native_translation_check(b,peer,contract,moves,timeout_s=2.)
for ref,delta in moves.items():fps[ref].Move(p.VECTOR2I_MM(*delta))
try:
 for row in barrels:
  if not row['unique_rigid_delta']:continue
  dx,dy=moves[row['active'][0]['ref']];v=next(t for t in tracks if force._uid(t)==row['source']['uuid']);at=p.VECTOR2I(v.GetPosition().x+round(dx*1e6),v.GetPosition().y+round(dy*1e6));block,recs=fab.via_at_pad_conflicts(b,at,v.GetWidth(v.TopLayer()),v.GetDrillValue(),v.GetNetCode());row.update(destination_mm=[at.x/1e6,at.y/1e6],pad_blocked=block is not None,pad_records=recs)
finally:
 for ref,delta in moves.items():fps[ref].Move(p.VECTOR2I_MM(-delta[0],-delta[1]))
r=dict(source=str(source.relative_to(ROOT)),source_sha256=sha,moves=moves,courtyard_collisions=collisions,paired_ok=paired['ok'],paired_violations=paired.get('violations'),C55_contacts=contacts,source_native_pad_or_dogbone_barrels=barrels,C55_horizontal_delta_to_clear_C54_courtyard_mm=translate(shapes['C54'],2,0).bounds[2]-shapes['C55'].bounds[0],scope='Source native pad/dogbone and body diagnostic only; ownership compiler, source-track-body barrels, complete copper/zone/body guards and restoration not waived',board_saved=False,accepted=False)
r['peer_source']=str(Path(peer.GetFileName()).relative_to(ROOT));r['peer_sha256']=force._hash(Path(peer.GetFileName()));r['stack_path']='beta/assembly/hub-atx-stack.json';r['stack_sha256']=force._hash(ROOT/r['stack_path'])
r['clearance_floor_mm']=.2;r['new_xy_compaction_mm']=[0,0];r['placement_targets']={ref:dict(x_mm=fp.GetPosition().x/1e6+moves.get(ref,(0,0))[0],y_mm=fp.GetPosition().y/1e6+moves.get(ref,(0,0))[1],rotation_deg=fp.GetOrientationDegrees())for ref,fp in fps.items()if ref in set(moves)|{'C51','C54','C55'}}
if simple:r['named_rejections']=dict(C9_GND_via_vertical_bus_signed_gap_mm=-.4727615,C27_GND_via_diagonal_bus_signed_gap_mm=-.131432781751871,minimum_C9_total_x_move_for_point2mm_clearance_mm=1.6727615)
else:r['named_rejections']=dict(C55_GND_pad_new_mm=[22.2,48],retained_foreign_power_track_uuid='36034a2e-3dd8-47d2-94be-dbed075d1a6e',retained_track_net='+5VSB',retained_track_start_mm=[22,47.5],retained_track_end_mm=[22,53],retained_track_width_nm=477370,requested_full_current_departure_target_x_mm=24.4,departure_y_and_exact_boundary_to_be_source_compiled=True,decision='Native body study passes, but old x22 full-current departure intersects moved C55 Ground land/branch. Exact source-owned rebuild toward x24.4 port required; no accepted routing.')
assert force._hash(source)==sha
(Path(__file__).parent/('geometry-rejected-plus1.json'if simple else 'geometry-coordinated-plus1p8.json')).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(courtyards=collisions,paired=paired['ok'],barrels=[(q['source']['uuid'],q.get('destination_mm'),q.get('pad_blocked'))for q in barrels],minimum_C55_delta=r['C55_horizontal_delta_to_clear_C54_courtyard_mm']),indent=2))
