import sys,json,math
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_fab_profile as fab
import cec_fr as fr
import cec_assembly_envelope as assembly
p,_=_native();folder=Path(__file__).parent;study=json.loads((folder/'geometry-fixed-ground-pivot.json').read_text());source=Path(study['source']);assert force._hash(source)==study['source_sha256'];b=p.LoadBoard(str(source));fps={f.GetReference():f for f in b.GetFootprints()};cap=fps['C54'];oldpos=tuple(cap.GetPosition());oldrot=cap.GetOrientationDegrees();via=next(t for t in b.GetTracks()if force._uid(t)=='c25714c1-f2d8-4e0e-9711-7d208ce1da97');original_via_at=tuple(via.GetPosition());source_process=fab.local_pofv_via_decision(b,via)
for ref,target in study['proposed_poses'].items():fps[ref].SetOrientationDegrees(target[2]);fps[ref].SetPosition(p.VECTOR2I(target[0],target[1]))
sup=next(q for q in cap.Pads()if q.GetNetname()!='GND');anchor=tuple(sup.GetPosition());cap.SetOrientationDegrees(cap.GetOrientationDegrees()+180);cap.Move(p.VECTOR2I(anchor[0]-sup.GetPosition().x,anchor[1]-sup.GetPosition().y-250000));newpos=tuple(cap.GetPosition());turn=math.radians(-(cap.GetOrientationDegrees()-oldrot));dx,dy=original_via_at[0]-oldpos[0],original_via_at[1]-oldpos[1];at=p.VECTOR2I(round(newpos[0]+math.cos(turn)*dx-math.sin(turn)*dy),round(newpos[1]+math.sin(turn)*dx+math.cos(turn)*dy));block,padrecords=fab.via_at_pad_conflicts(b,at,via.GetWidth(via.TopLayer()),via.GetDrillValue(),via.GetNetCode());guard={};clear=fr._via_spot_clear(b,at,via.GetWidth(via.TopLayer()),200000,{via.GetNetCode()},drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),existing_via_uuid=force._uid(via),foreign_cache={},report=guard)
# A moved trial must not borrow an existing-via identity at a different axis.
centered='--centered-via'in sys.argv
if centered:
 at=next(q for q in cap.Pads()if q.GetNetname()=='GND').GetPosition()
 block,padrecords=fab.via_at_pad_conflicts(b,at,via.GetWidth(via.TopLayer()),via.GetDrillValue(),via.GetNetCode())
guard={};clear=fr._via_spot_clear(b,at,via.GetWidth(via.TopLayer()),200000,{via.GetNetCode()},drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),foreign_cache={},report=guard)
probe=p.PCB_VIA(b);probe.SetPosition(at);probe.SetWidth(via.GetWidth(via.TopLayer()));probe.SetDrill(via.GetDrillValue());probe.SetLayerPair(p.F_Cu,p.B_Cu);probe.SetNetCode(via.GetNetCode());foreign=[]
for t in b.GetTracks():
 if t.GetNetCode()==via.GetNetCode():continue
 for l in b.GetEnabledLayers().CuStack():
  if t.IsOnLayer(l)and t.GetEffectiveShape(l).Collide(probe.GetEffectiveShape(l),200000):foreign.append(dict(uuid=force._uid(t),net=t.GetNetname(),layer=b.GetLayerName(l),start_nm=list(t.GetStart()),end_nm=list(t.GetEnd())))
shapes={}
for ref,fp in fps.items():
 try:shapes[ref]=assembly.footprint_planar_envelope(fp)[0]
 except ValueError:pass
refs=set(study['proposed_poses']);coll=[]
for ref in refs:
 for other,shape in shapes.items():
  if ref!=other and fps[ref].GetLayer()==fps[other].GetLayer()and shapes[ref].intersects(shape):coll.append([ref,other])
peer=ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb';stack=ROOT/'beta/assembly/hub-atx-stack.json';paired,_=assembly.evaluate_boards(b,p.LoadBoard(str(peer)),json.loads(stack.read_text()))
points=[(17.67499,47.775001),(18.62499,47.775001),(18.92499,47.475001),(19.024999,47.475001),(20.4,46.1)];net=b.GetNetcodeFromNetname('+5VSB');idx=fr._identified_foreign_shape_indexes(b,p.F_Cu,{net});legs=[]
for a,z in zip(points,points[1:]):legs.append(dict(start_mm=a,end_mm=z,foreign_clear=fr._tap_foreign_clear(b,p.VECTOR2I_MM(*a),p.VECTOR2I_MM(*z),477370,p.F_Cu,200000,{net}),blockers=fr._snapshot_foreign_blockers(p.VECTOR2I_MM(*a),p.VECTOR2I_MM(*z),477370,200000,*idx,limit=8)))
out=dict(source_sha256=study['source_sha256'],peer_sha256=force._hash(peer),stack_sha256=force._hash(stack),C54_target=[newpos[0],newpos[1],cap.GetOrientationDegrees()],C54_pad_positions=[dict(pin=q.GetNumber(),net=q.GetNetname(),at_nm=list(q.GetPosition()))for q in cap.Pads()],source_via_uuid=force._uid(via),source_via_at_nm=original_via_at,source_via_process=source_process,proposed_via_at_nm=list(at),proposed_via_geometry_nm=[via.GetWidth(via.TopLayer()),via.GetDrillValue()],destination_pad_blocked=block is not None,destination_pad_records=padrecords,all_layer_clear=clear,all_layer_guard=guard,actual_foreign_track_conflicts=foreign,courtyard_collisions=coll,paired_ok=paired['ok'],paired_violations=paired['violations'],full_width_local_path_legs=legs,path_width_nm=477370,path_length_mm=sum(math.dist(a,z)for a,z in zip(points,points[1:])),locality_limit_mm=3.5,net_correction='C54/C55 supply is +5VSB at U6.IN1 pin7, NOT U6.OUT pin1(5VSB_MUX).',board_saved=False,accepted=False)
out['retained_B3V3_diagonal_signed_copper_gap_mm']=abs(at.y/1e6-at.x/1e6-24.2)/math.sqrt(2)-6.535523/2-.5/2
owner_pad=next(q for q in fps['U6'].Pads()if q.GetNumber()=='7')
assert force._uid(owner_pad)=='b7f83a9b-fcdb-47ff-9829-b6bba23efd1c'
out['canonical_owner_endpoint']=dict(reference='U6',pin='7',role='IN1',pad_uuid=force._uid(owner_pad),net=owner_pad.GetNetname(),at_nm=list(owner_pad.GetPosition()))
out['rigid_source_pad_partial_overlap_bound_mm']=.1+.5/2-.62/2
out['centered_Ground_via_study_not_rigid_transport']=centered
filled=[];unknown=[]
for zone in b.Zones():
 if zone.GetIsRuleArea()or zone.GetNetCode()==via.GetNetCode():continue
 for layer in b.GetEnabledLayers().CuStack():
  if not zone.IsOnLayer(layer):continue
  record=dict(uuid=force._uid(zone),net=zone.GetNetname(),layer=b.GetLayerName(layer))
  if not zone.IsFilled()or not zone.HasFilledPolysForLayer(layer):unknown.append(record)
  elif zone.GetFilledPolysList(layer).Collide(probe.GetEffectiveShape(layer),200000):filled.append(record)
out['saved_filled_zone_conflicts']=filled;out['unknown_saved_zone_fills']=unknown
assert force._hash(source)==study['source_sha256']
name='geometry-flipped-C54-up0p25-centered-via.json'if centered else 'geometry-flipped-C54-up0p25.json'
(folder/name).write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items()if k not in ['full_width_local_path_legs']},indent=2))
