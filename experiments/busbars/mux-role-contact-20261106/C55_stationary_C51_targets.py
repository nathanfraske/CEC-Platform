"""Three dimension-led C55 targets; C51 and VBUS barrel stay literal Source."""
import json
import math
from pathlib import Path
import sys
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_assembly_envelope as assembly
import cec_fab_profile as fab
import cec_fr as fr
p,_=_native();folder=Path(__file__).parent;study=json.loads((folder/'geometry.json').read_text())
source=ROOT/study['source'];assert force._hash(source)==study['source_sha256']
cases=[('horizontal_left',[20900000,46240000,0]),('horizontal_right',[21050000,46240000,0]),
 ('vertical_right_up',[20960000,49150000,270])]
rows=[]
for name,target in cases:
 b=p.LoadBoard(str(source));fps={f.GetReference():f for f in b.GetFootprints()}
 for ref,pose in study['proposed_poses'].items():
  if ref in ('C51','C55'):continue
  fps[ref].SetOrientationDegrees(pose[2]);fps[ref].SetPosition(p.VECTOR2I(*pose[:2]))
 fps['C55'].SetOrientationDegrees(target[2]);fps['C55'].SetPosition(p.VECTOR2I(*target[:2]))
 shapes={}
 for ref,fp in fps.items():
  try:shapes[ref]=assembly.footprint_planar_envelope(fp)[0]
  except ValueError:pass
 clashes=[]
 for other,shape in shapes.items():
  if other=='C55'or fps[other].GetLayer()!=fps['C55'].GetLayer():continue
  inter=shape.intersection(shapes['C55'])
  if not inter.is_empty:clashes.append(dict(ref=other,area_mm2=inter.area,bounds_mm=list(inter.bounds)))
 paired,_=assembly.evaluate_boards(b,p.LoadBoard(str(ROOT/study['peer'])),json.loads((ROOT/study['stack']).read_text()))
 pads={q.GetNumber():q for q in fps['C55'].Pads()};pad_conflicts=[]
 for pin,pad in pads.items():
  for other in [*(q for f in b.GetFootprints()for q in f.Pads()),*b.GetTracks()]:
   if other.GetNetCode()==pad.GetNetCode():continue
   for face in pad.GetLayerSet().CuStack():
    if not other.IsOnLayer(face):continue
    shape=pad.GetEffectiveShape(face)
    hit=shape.Collide(other.GetPosition(),other.GetWidth(face)//2+200000)if other.GetClass()=='PCB_VIA'else shape.Collide(other.GetEffectiveShape(face),200000)
    if hit:pad_conflicts.append(dict(pin=pin,uuid=force._uid(other),kind=other.GetClass(),net=other.GetNetname(),
     ref=other.GetParentFootprint().GetReference()if other.GetClass()=='PAD'else None,layer=int(face)))
 at=pads['2'].GetPosition();code=pads['2'].GetNetCode();blocked,records=fab.via_at_pad_conflicts(b,at,500000,300000,code)
 report={};clear=fr._via_spot_clear(b,at,500000,200000,{code},drill_nm=300000,net_code=code,foreign_cache={},report=report)
 v=p.PCB_VIA(b);v.SetPosition(at);v.SetWidth(500000);v.SetDrill(300000);v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetNetCode(code)
 filled=[]
 for z in b.Zones():
  if z.GetIsRuleArea()or z.GetNetCode()==code:continue
  for face in v.GetLayerSet().CuStack():
   if z.IsOnLayer(face)and z.IsFilled()and z.HasFilledPolysForLayer(face)and z.GetFilledPolysList(face).Collide(v.GetEffectiveShape(face),200000):
    filled.append(dict(uuid=force._uid(z),net=z.GetNetname(),layer=b.GetLayerName(face)))
 if target[2]==0:
  sup=[x/1e6 for x in pads['1'].GetPosition()]
  points=[(17.67499,47.775001),(18.799989,47.775001),(18.92499,47.65),
   (18.92499,sup[1]+sup[0]-18.92499),tuple(sup)]
 else:points=[(17.67499,47.775001),(20.535001,47.775001),(20.96,48.2)]
 code=b.GetNetcodeFromNetname('+5VSB');idx=fr._identified_foreign_shape_indexes(b,p.F_Cu,{code});legs=[]
 for a,z in zip(points,points[1:]):
  first,last=p.VECTOR2I_MM(*a),p.VECTOR2I_MM(*z)
  legs.append(dict(a_mm=a,b_mm=z,foreign_clear=fr._tap_foreign_clear(b,first,last,477370,p.F_Cu,200000,{code}),
   blockers=fr._snapshot_foreign_blockers(first,last,477370,200000,*idx,limit=12),edge_clear=fr._edge_leg_clear(b,first,last,238685),
   native_rule_hits=force._native_track_rule_hits(b,p.SHAPE_SEGMENT(first,last,477370),p.F_Cu)))
 rows.append(dict(name=name,C55_pose_nm_deg=target,C55_courtyard_bounds_mm=list(shapes['C55'].bounds),courtyard_collisions=clashes,
  paired_ok=paired['ok'],paired_violations=paired['violations'],pad_positions={pin:list(q.GetPosition())for pin,q in pads.items()},
  moved_pad_retained_foreign_copper_200um_conflicts=pad_conflicts,
  hypothetical_centered_Ground_via=dict(at_nm=list(at),diameter_nm=500000,drill_nm=300000,pad_process_blocked=blocked is not None,
   process_records=records,all_layer_spot_clear=clear,all_layer_report=report,actual_saved_foreign_filled_zone_conflicts=filled),
  IN1_to_C55_SUP_full_width_path=dict(width_nm=477370,layer='F.Cu',points_mm=points,legs=legs,
   length_mm=sum(math.dist(a,z)for a,z in zip(points,points[1:])),maximum_mm=3.5,
   C54_SUP_is_explicit_path_endpoint_or_actual_intersected_land=True)))
assert force._hash(source)==study['source_sha256']
out=dict(source=study['source'],source_sha256=study['source_sha256'],peer_sha256=study['peer_sha256'],stack_sha256=study['stack_sha256'],
 C51_exact_Source_pose=[18500000,50125000,180],VBUS_barrel_unchanged=True,other_six_base_poses=study['proposed_poses'],cases=rows,
 all_original_tracks_and_barrels_retained=True,board_saved=False,cut_or_reseat_authority=False,release_authority=False)
(folder/'C55-stationary-C51-three-targets.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(rows,indent=2))
