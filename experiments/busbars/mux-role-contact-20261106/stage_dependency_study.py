"""Final-pose subsets only: no alternative poses, sweeps or board saves."""
import json
import argparse
import math
from pathlib import Path
import sys
import time
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_control_gate_bias_placement as native
import cec_assembly_envelope as assembly
import cec_fab_profile as fab
p,_=_native();folder=Path(__file__).parent
study=json.loads((folder/'geometry.json').read_text());source=ROOT/study['source'];assert force._hash(source)==study['source_sha256']
poses=study['proposed_poses'];peer=ROOT/study['peer'];stack=ROOT/study['stack']
parser=argparse.ArgumentParser();parser.add_argument('--two-c51-final',action='store_true');parser.add_argument('--c51-clearance-root',action='store_true');args=parser.parse_args()
cases=[('C51_first',['C51']),('C55_after_C51',['C51','C55']),('C54_after_C51',['C51','C54']),
    ('four_part_U6_cell_after_C51',['C51','U6','C9','C27','R54']),('six_part_completion_after_C51',list(poses)),
    ('six_part_final_C51_exact_source',[r for r in poses if r!='C51'])]
if args.two_c51_final:
 cases=[('C51_final_same_Y',list(poses)),('C51_final_down_0p3',list(poses))]
root_result=None
if args.c51_clearance_root:
 probe=p.LoadBoard(str(source));cap=probe.FindFootprintByReference('C51');cap.SetOrientationDegrees(180)
 vb=next(t for t in probe.GetTracks()if force._uid(t)=='55854f89-ed41-4d19-a9cf-3973838c13d3')
 lo,hi=50125000,50425000;steps=[]
 for _ in range(16):
  mid=(lo+hi)//2;cap.SetPosition(p.VECTOR2I(18300000,mid))
  collides=bool(cap.FindPadByNumber('2').GetEffectiveShape(p.F_Cu).Collide(vb.GetPosition(),vb.GetWidth(p.F_Cu)//2+210000))
  steps.append(dict(y_nm=mid,violates_210000nm=collides))
  if collides:lo=mid
  else:hi=mid
 root_result=dict(last_refused_y_nm=lo,first_clear_y_nm=hi,bisections=steps,target_clearance_nm=210000)
 cases=[('C51_clearance_root',list(poses))]
rows=[]
for name,refs in cases:
 b=p.LoadBoard(str(source));fps={f.GetReference():f for f in b.GetFootprints()}
 targets={r:list(v)for r,v in poses.items()}
 if name=='C51_final_same_Y':targets['C51']=[18300000,50125000,180]
 if name=='C51_final_down_0p3':targets['C51']=[18300000,50425000,180]
 if name=='C51_clearance_root':targets['C51']=[18300000,root_result['first_clear_y_nm'],180]
 original_C51={q.GetNumber():native._direct_contacts(b,q,time.monotonic()+2.) for q in fps['C51'].Pads()}
 for ref in refs:
  pose=targets[ref];fps[ref].SetOrientationDegrees(pose[2]);fps[ref].SetPosition(p.VECTOR2I(*pose[:2]))
 shapes={}
 for ref,fp in fps.items():
  try:shapes[ref]=assembly.footprint_planar_envelope(fp)[0]
  except ValueError:pass
 clashes=[];seen=set()
 for ref in refs:
  for other,shape in shapes.items():
   pair=tuple(sorted((ref,other)))
   if ref==other or pair in seen or fps[ref].GetLayer()!=fps[other].GetLayer():continue
   seen.add(pair);hit=shapes[ref].intersection(shape)
   if not hit.is_empty:clashes.append(dict(refs=pair,intersection_area_mm2=hit.area,
    intersection_bounds_mm=list(hit.bounds),first_courtyard_bounds_mm=list(shapes[ref].bounds),
    second_courtyard_bounds_mm=list(shape.bounds)))
 owner=fps['U6'].FindPadByNumber('7');distances={}
 for ref in ('C54','C55'):
  sup=fps[ref].FindPadByNumber('1');distances[ref]=dict(cap_SUP_nm=list(sup.GetPosition()),U6_IN1_nm=list(owner.GetPosition()),
   direct_mm=math.dist(list(sup.GetPosition()),list(owner.GetPosition()))/1e6,
   source_same_face_full_width_path_limit_mm=3.5,direct_is_only_necessary_lower_bound=True)
 row=dict(name=name,final_target_refs=refs,actual_target_poses={r:targets[r]for r in refs},courtyard_clashes=clashes,IN1_direct_distance_lower_bounds=distances)
 if name in ('C51_first','six_part_final_C51_exact_source','C51_final_same_Y','C51_final_down_0p3','C51_clearance_root'):
  paired,_=assembly.evaluate_boards(b,p.LoadBoard(str(peer)),json.loads(stack.read_text()))
  row.update(paired_ok=paired['ok'],paired_violations=paired['violations'])
  contacts={q.GetNumber():native._direct_contacts(b,q,time.monotonic()+2.) for q in fps['C51'].Pads()}
  row['C51_source_contact_ids']={pin:sorted(c['item_uuid'] for c in cs) for pin,cs in original_C51.items()}
  row['C51_posed_contact_ids']={pin:sorted(c['item_uuid'] for c in cs) for pin,cs in contacts.items()}
  row['C51_all_original_native_terminal_contacts_still_present']=all(set(row['C51_source_contact_ids'][pin])<=set(row['C51_posed_contact_ids'][pin])for pin in contacts)
  oldvia=next(t for t in b.GetTracks()if force._uid(t)=='7f4e567d-2755-4c6e-a51c-2af6b999bc20')
  blocked,records=fab.via_at_pad_conflicts(b,oldvia.GetPosition(),oldvia.GetWidth(oldvia.TopLayer()),oldvia.GetDrillValue(),oldvia.GetNetCode())
  row.update(retained_C51_Ground_via_process_blocked=blocked is not None,retained_C51_Ground_via_process_records=records)
  hits=[]
  for pad in fps['C51'].Pads():
   for other in [*(q for f in b.GetFootprints()for q in f.Pads()),*b.GetTracks()]:
    if other.GetNetCode()==pad.GetNetCode():continue
    for face in pad.GetLayerSet().CuStack():
     if not other.IsOnLayer(face):continue
     shape=pad.GetEffectiveShape(face)
     hit=shape.Collide(other.GetPosition(),other.GetWidth(face)//2+200000)if other.GetClass()=='PCB_VIA'else shape.Collide(other.GetEffectiveShape(face),200000)
     if hit:hits.append(dict(pad=pad.GetNumber(),uuid=force._uid(other),kind=other.GetClass(),net=other.GetNetname(),layer=int(face)))
  row['C51_moved_pad_retained_foreign_copper_200um_conflicts']=hits
  vb=next(t for t in b.GetTracks()if force._uid(t)=='55854f89-ed41-4d19-a9cf-3973838c13d3')
  old_board=p.LoadBoard(str(source));oldpad=old_board.FindFootprintByReference('C51').FindPadByNumber('2')
  newpad=fps['C51'].FindPadByNumber('2')
  def edge_clearance(pad):
   shape=pad.GetEffectiveShape(p.F_Cu);radius=vb.GetWidth(p.F_Cu)//2;lo,hi=0,2_000_000
   while hi-lo>1:
    mid=(lo+hi)//2
    if shape.Collide(vb.GetPosition(),radius+mid):hi=mid
    else:lo=mid
   return dict(native_max_noncolliding_clearance_nm=lo,native_min_colliding_clearance_nm=hi,
    physical_overlap=bool(shape.Collide(vb.GetPosition(),radius)))
  row['C51_Ground_to_fixed_VBUS_barrel_clearance']=dict(via_uuid=force._uid(vb),at_nm=list(vb.GetPosition()),
   diameter_nm=vb.GetWidth(p.F_Cu),drill_nm=vb.GetDrillValue(),source=edge_clearance(oldpad),proposed=edge_clearance(newpad),
   required_clearance_nm=200000)
  control=fps['U6'].FindPadByNumber('11');signal=fps['C51'].FindPadByNumber('1')
  row['SS_control_endpoints']=dict(U6_SS_pad_uuid=force._uid(control),U6_SS_nm=list(control.GetPosition()),
   C51_SS_pad_uuid=force._uid(signal),C51_SS_nm=list(signal.GetPosition()),
   direct_mm=math.dist(list(control.GetPosition()),list(signal.GetPosition()))/1e6,
   C51_is_timing_control_cap_not_selected_supply_bypass=True,
   no_supply_bypass_distance_or_current_credit=True,
   SS_route_still_must_rebuild_complete_original_native_contacts=True)
 rows.append(row)
assert force._hash(source)==study['source_sha256']
out=dict(source=study['source'],source_sha256=study['source_sha256'],peer_sha256=force._hash(peer),stack_sha256=force._hash(stack),clearance_root=root_result,
 fixed_final_targets=poses,cases=rows,board_saved=False,source_copper_retained=True,cut_or_route_authority=False,release_authority=False)
target=folder/('C51-clearance-root.json'if args.c51_clearance_root else 'two-C51-final-targets.json'if args.two_c51_final else 'stage-dependency-study.json')
target.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(rows,indent=2))
