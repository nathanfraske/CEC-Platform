"""One root-specified map-derived native study; no search or source cuts."""
import sys,json,math
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_fab_profile as fab
import cec_fr as fr
import cec_assembly_envelope as assembly
p,_=_native();folder=Path(__file__).parent;source=ROOT/'experiments/busbars/cap-ground-repair-20261106/candidate/board.kicad_pcb';sha=force._hash(source);assert sha=='1512d4f046daebaba629ac29db4bc5caf2d53bc6ccf370e44deb903c4259b045';b=p.LoadBoard(str(source));fps={f.GetReference():f for f in b.GetFootprints()};poses={r:[fps[r].GetPosition().x+2000000,fps[r].GetPosition().y,fps[r].GetOrientationDegrees()]for r in ['U6','C9','C27','R54']};source_C51_angle=fps['C51'].GetOrientationDegrees();poses.update(C54=[18924990,48130000,270],C55=[20800000,49350000,270],C51=[18300000,49925000,source_C51_angle])
for r,q in poses.items():fps[r].SetOrientationDegrees(q[2]);fps[r].SetPosition(p.VECTOR2I(q[0],q[1]))
shapes={}
for ref,fp in fps.items():
 try:shapes[ref]=assembly.footprint_planar_envelope(fp)[0]
 except ValueError:pass
coll=[];seen=set()
for ref in poses:
 for other,g in shapes.items():
  key=tuple(sorted((ref,other)))
  if other==ref or key in seen or fps[ref].GetLayer()!=fps[other].GetLayer():continue
  seen.add(key);inter=shapes[ref].intersection(g)
  if not inter.is_empty:coll.append(dict(refs=key,area_mm2=inter.area,bounds=[list(shapes[ref].bounds),list(g.bounds)]))
peer=ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb';stack=ROOT/'beta/assembly/hub-atx-stack.json';paired,_=assembly.evaluate_boards(b,p.LoadBoard(str(peer)),json.loads(stack.read_text()));vias=[]
for ref in ['C54','C55']:
 pad=next(q for q in fps[ref].Pads()if q.GetNumber()=='2');at=pad.GetPosition();code=pad.GetNetCode();via=p.PCB_VIA(b);via.SetPosition(at);via.SetWidth(500000);via.SetDrill(300000);via.SetLayerPair(p.F_Cu,p.B_Cu);via.SetNetCode(code);block,records=fab.via_at_pad_conflicts(b,at,500000,300000,code);report={};existing='c25714c1-f2d8-4e0e-9711-7d208ce1da97'if ref=='C54'else None
 # Retain source copper and original holes; exclusions are not permissions.
 clear=fr._via_spot_clear(b,at,500000,200000,{code},drill_nm=300000,net_code=code,foreign_cache={},report=report);actual=[]
 for t in b.GetTracks():
  if t.GetNetCode()==code:continue
  for l in b.GetEnabledLayers().CuStack():
   if t.IsOnLayer(l)and t.GetEffectiveShape(l).Collide(via.GetEffectiveShape(l),200000):actual.append(dict(uuid=force._uid(t),net=t.GetNetname(),layer=b.GetLayerName(l),kind=t.GetClass(),start_nm=list(t.GetStart()),end_nm=list(t.GetEnd())))
 filled=[];unknown=[]
 for zone in b.Zones():
  if zone.GetIsRuleArea()or zone.GetNetCode()==code:continue
  for layer in b.GetEnabledLayers().CuStack():
   if not zone.IsOnLayer(layer):continue
   if not zone.IsFilled()or not zone.HasFilledPolysForLayer(layer):
    if zone.Outline().Collide(via.GetEffectiveShape(layer),200000):unknown.append(dict(uuid=force._uid(zone),net=zone.GetNetname(),layer=b.GetLayerName(layer)))
   elif zone.GetFilledPolysList(layer).Collide(via.GetEffectiveShape(layer),200000):filled.append(dict(uuid=force._uid(zone),net=zone.GetNetname(),layer=b.GetLayerName(layer)))
 vias.append(dict(ref=ref,at_nm=list(at),diameter_nm=500000,drill_nm=300000,pad_process_blocked=block is not None,pad_process_records=records,all_layer_clear=clear,all_layer_report=report,actual_foreign_tracks=actual,actual_saved_foreign_filled_zone_conflicts=filled,unknown_saved_zone_geometry=unknown,source_barrel_replacement_requires_positive_exclusive_ownership=True,retired_source_barrel_uuid=existing if ref=='C54'else'8fcb6331-0f3f-403a-ba73-e7a6da00710b'))
v51=next(t for t in b.GetTracks()if force._uid(t)=='7f4e567d-2755-4c6e-a51c-2af6b999bc20');b51,r51=fab.via_at_pad_conflicts(b,v51.GetPosition(),v51.GetWidth(v51.TopLayer()),v51.GetDrillValue(),v51.GetNetCode());points=[(17.67499,47.775001),(18.799989,47.775001),(18.92499,47.65),(20.05,47.65),(20.8,48.4)];net=b.GetNetcodeFromNetname('+5VSB');idx=fr._identified_foreign_shape_indexes(b,p.F_Cu,{net});legs=[]
for a,z in zip(points,points[1:]):legs.append(dict(a_mm=a,z_mm=z,clear=fr._tap_foreign_clear(b,p.VECTOR2I_MM(*a),p.VECTOR2I_MM(*z),477370,p.F_Cu,200000,{net}),blockers=fr._snapshot_foreign_blockers(p.VECTOR2I_MM(*a),p.VECTOR2I_MM(*z),477370,200000,*idx,limit=10)))
out=dict(source=str(source.relative_to(ROOT)),source_sha256=sha,peer_sha256=force._hash(peer),stack_sha256=force._hash(stack),source_C51_rotation_deg=source_C51_angle,source_C51_unchanged_rotation_intent_over_literal_zero=True,proposed_poses=poses,native_courtyards={r:list(shapes[r].bounds)for r in poses},court_clashes=coll,paired_ok=paired['ok'],paired_violations=paired['violations'],hypothetical_ground_vias=vias,retained_C51_via_process_blocked=b51 is not None,retained_C51_via_process_records=r51,retained_C51_via_at_nm=list(v51.GetPosition()),C51_new_pad_positions=[dict(pin=q.GetNumber(),net=q.GetNetname(),at_nm=list(q.GetPosition()))for q in fps['C51'].Pads()],full_width_IN1_local_path=legs,path_length_mm=sum(math.dist(a,z)for a,z in zip(points,points[1:])),width_nm=477370,locality_limit_mm=3.5,source_copper_retained=True,source_C55_old_tail_and_via_exclusive_retirement_pending=True,board_saved=False,accepted=False,release_authority=False)
assert force._hash(source)==sha;(folder/'geometry-map-derived-seven.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k not in('full_width_IN1_local_path','proposed_poses','native_courtyards')},indent=2))
