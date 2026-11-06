"""Actual c4 VBUS barrel contacts and bounded hand-chosen geometry probes."""
import argparse
import json
from pathlib import Path
import sys
import time
import math
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_aggregate_cap_ground_leaf as native
import cec_control_gate_bias_placement as identity
import cec_full_current_planar_reflow as full
import cec_fr as fr
import cec_fab_profile as fab
p,_=_native();folder=Path(__file__).parent
parser=argparse.ArgumentParser();parser.add_argument('--seats',action='store_true');args=parser.parse_args()
study=json.loads((folder/'geometry.json').read_text());source=ROOT/study['source'];assert force._hash(source)==study['source_sha256']
b=p.LoadBoard(str(source));items=native._objects(b);uid='55854f89-ed41-4d19-a9cf-3973838c13d3';via=items[uid]
deadline=time.monotonic()+9.
def desc(item):
 d=dict(uuid=force._uid(item),kind=item.GetClass(),net=item.GetNetname(),locked=bool(item.IsLocked()),groups=identity._groups(b,item))
 if item.GetClass()=='PAD':d.update(ref=item.GetParentFootprint().GetReference(),pin=item.GetNumber(),at_nm=list(item.GetPosition()))
 elif item.GetClass()=='PCB_TRACK':d.update(start_nm=list(item.GetStart()),end_nm=list(item.GetEnd()),width_nm=item.GetWidth(),layer=int(item.GetLayer()))
 elif item.GetClass()=='PCB_VIA':d.update(at_nm=list(item.GetPosition()),drill_nm=item.GetDrillValue(),top=int(item.TopLayer()),bottom=int(item.BottomLayer()),
  diameter_by_layer_nm={str(l):item.GetWidth(l)for l in item.GetLayerSet().CuStack()})
 return d
contacts=[]
for face in via.GetLayerSet().CuStack():
 holes=[i for i in items.values()if i.IsOnLayer(face)and(i.GetClass()=='PCB_VIA'or i.GetClass()=='PAD'and i.HasHole())]
 for other in items.values():
  if force._uid(other)==uid or not other.IsOnLayer(face):continue
  area=native._contact(via,other,face,holes,deadline)
  if area is not None:contacts.append(dict(layer_id=int(face),layer=b.GetLayerName(face),material=desc(other),actual_lower_contact_nm2=area.Area()))
kind,domain,contract=full._model(b,source,via.GetNetname(),'atx-24pin-rev3')
out=dict(source=study['source'],source_sha256=study['source_sha256'],source_barrel=desc(via),complete_original_all_layer_actual_contacts=contacts,
 existing_current_domain_kind=kind,current_domain=domain,current_contract=contract,
 per_contact_face_full_current_floor_nm={str(c['layer_id']):full._source_width_floor(b,source,contract,c['layer_id'])for c in contacts if c['material']['kind']=='PCB_TRACK'},
 source_process=fab.via_at_pad_conflicts(b,via.GetPosition(),via.GetWidth(via.TopLayer()),via.GetDrillValue(),via.GetNetCode())[1],
 barrel_current_rating_inferred=False,ordinary_signal_reseat_authority=False,barrel_relocation_or_cut_permission=False,
 board_saved=False,release_authority=False)
(folder/'VBUS-barrel-source-contacts.json').write_text(json.dumps(out,indent=2)+'\n')
if args.seats:
 for ref,pose in study['proposed_poses'].items():
  fp=b.FindFootprintByReference(ref);fp.SetOrientationDegrees(pose[2]);fp.SetPosition(p.VECTOR2I(*pose[:2]))
 projected=json.loads((folder/'contacts.json').read_text())['barrels_with_actual_direct_or_incident_leaf_contact']
 candidates=[('minimal_left',(16.59,49.5),[(16.45,49.8),(16.45,49.64),(16.59,49.5)],[(16.75,52.75),(16.75,49.66),(16.59,49.5)]),
  ('above_C51',(16.75,49.19),[(16.45,49.8),(16.45,49.49),(16.75,49.19)],[(16.75,52.75),(16.75,49.19)]),
  ('below_C51',(16.75,50.75),[(16.45,49.8),(16.45,50.45),(16.75,50.75)],[(16.75,52.75),(16.75,50.75)])]
 results=[];code=via.GetNetCode()
 for name,at,front,back in candidates:
  center=p.VECTOR2I_MM(*at);via.SetPosition(center);blocked,records=fab.via_at_pad_conflicts(b,center,600000,300000,code)
  report={};spot=fr._via_spot_clear(b,center,600000,200000,{code},drill_nm=300000,net_code=code,
   existing_via_uuid=uid,foreign_cache={},report=report)
  filled=[];unknown=[]
  for zone in b.Zones():
   if zone.GetIsRuleArea()or zone.GetNetCode()==code:continue
   for face in via.GetLayerSet().CuStack():
    if not zone.IsOnLayer(face):continue
    record=dict(uuid=force._uid(zone),net=zone.GetNetname(),layer=b.GetLayerName(face))
    if not zone.IsFilled()or not zone.HasFilledPolysForLayer(face):
     if zone.Outline().Collide(via.GetEffectiveShape(face),200000):unknown.append(record)
    elif zone.GetFilledPolysList(face).Collide(via.GetEffectiveShape(face),200000):filled.append(record)
  conservative=[]
  for item in projected:
   saved=item['source_barrel']
   if saved['net']==via.GetNetname():continue
   axis=item['unique_projected_axis_nm']
   if saved['uuid']=='7f4e567d-2755-4c6e-a51c-2af6b999bc20':axis=saved['at_nm']
   if saved['uuid']=='d2fedf54-0311-4cc8-a12e-77fc07fd3d4c':axis=saved['at_nm']
   if saved['uuid']=='8fcb6331-0f3f-403a-ba73-e7a6da00710b':axis=[20500000,50540000]
   if axis is None:continue
   radius=int(saved['diameter_by_layer_nm']['0'])//2
   distance=math.dist(list(center),axis)
   if distance<300000+radius+200000:
    conservative.append(dict(uuid=saved['uuid'],net=saved['net'],axis_nm=axis,diameter_nm=radius*2,
     center_distance_mm=distance/1e6,required_copper_center_distance_mm=(300000+radius+200000)/1e6,
     physical_overlap=distance<300000+radius,diagnostic_source_owned_projection_not_admitted=True))
  paths=[]
  for face,points in [(p.F_Cu,front),(p.B_Cu,back)]:
   idx=fr._identified_foreign_shape_indexes(b,face,{code});legs=[]
   for first,last in zip(points,points[1:]):
    a,z=p.VECTOR2I_MM(*first),p.VECTOR2I_MM(*last)
    legs.append(dict(a_mm=first,b_mm=last,foreign_clear=fr._tap_foreign_clear(b,a,z,200000,face,200000,{code}),
     foreign_blockers=fr._snapshot_foreign_blockers(a,z,200000,200000,*idx,limit=12),
     edge_clear=fr._edge_leg_clear(b,a,z,100000),native_rule_hits=force._native_track_rule_hits(b,p.SHAPE_SEGMENT(a,z,200000),face)))
   paths.append(dict(layer_id=int(face),layer=b.GetLayerName(face),width_nm=200000,points_mm=points,
    length_mm=sum(math.dist(a,z)for a,z in zip(points,points[1:])),legs=legs))
  results.append(dict(name=name,center_mm=at,diameter_nm=600000,drill_nm=300000,pad_process_blocked=blocked is not None,
   pad_process_records=records,all_layer_spot_clear=spot,all_layer_report=report,
   actual_saved_foreign_filled_zone_conflicts=filled,unknown_saved_zone_geometry=unknown,
   conservative_projected_barrel_conflicts=conservative,full_original_width_endpoint_paths=paths))
 via.SetPosition(p.VECTOR2I(*out['source_barrel']['at_nm']))
 out.update(exact_seven_footprint_poses_retained=study['proposed_poses'],candidates=results,
  candidate_axes_and_paths_are_geometry_only=True,all_original_saved_track_and_zone_material_retained=True,
  hypothetical_barrel_position_changed_in_RAM_only=True)
 (folder/'VBUS-barrel-three-seat-scout.json').write_text(json.dumps(out,indent=2)+'\n')
 print(json.dumps(dict(source_sha256=out['source_sha256'],candidates=results),indent=2))
else:print(json.dumps(out,indent=2))
assert force._hash(source)==study['source_sha256']
