"""One exact native via-centering repair; no board, footprint or track saves."""
import sys,json
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_fab_profile as fab
import cec_fr as fr
import cec_decoupler_cell as cells
p,_=_native();folder=Path(__file__).parent;source=ROOT/'experiments/busbars/coherent-mux-20261106/port-repaired-v1/candidate/board.kicad_pcb';sha='d4cf0b22f92526b6bdca0ae7cfa09af02217647db984577064ce91bfc177958a';assert force._hash(source)==sha;b=p.LoadBoard(str(source));uid='c25714c1-f2d8-4e0e-9711-7d208ce1da97';via=next(t for t in b.GetTracks()if force._uid(t)==uid);fp=next(f for f in b.GetFootprints()if f.GetReference()=='C54');pad=next(q for q in fp.Pads()if q.GetNumber()=='2');origin=tuple(via.GetPosition());target=tuple(pad.GetPosition());layers=list(via.GetLayerSet().CuStack());tracks=list(b.GetTracks());pads=[q for f in b.GetFootprints()for q in f.Pads()]
def inventory():
 direct=[];foreign=[];planes=[];unknown=[]
 for l in layers:
  shape=via.GetEffectiveShape(l)
  for item in [*pads,*tracks]:
   if force._uid(item)==uid or not item.IsOnLayer(l):continue
   effective=item.GetEffectiveShape(l);row=dict(uuid=force._uid(item),kind=item.GetClass(),net=item.GetNetname(),layer=b.GetLayerName(l))
   if item.GetClass()=='PAD':row.update(ref=item.GetParentFootprint().GetReference(),pin=item.GetNumber(),attribute=int(item.GetAttribute()))
   elif item.GetClass()=='PCB_TRACK':row.update(start_nm=list(item.GetStart()),end_nm=list(item.GetEnd()),width_nm=item.GetWidth(),locked=item.IsLocked())
   if effective.Collide(shape,0):direct.append(row)
   if item.GetNetCode()!=via.GetNetCode()and effective.Collide(shape,200000):foreign.append(row)
  for z in b.Zones():
   if z.GetIsRuleArea()or not z.IsOnLayer(l):continue
   row=dict(uuid=force._uid(z),net=z.GetNetname(),layer=b.GetLayerName(l),name=z.GetZoneName())
   if not z.IsFilled()or not z.HasFilledPolysForLayer(l):
    if z.Outline().Collide(shape,0):unknown.append(row)
    continue
   poly=z.GetFilledPolysList(l)
   if poly.Collide(shape,0):planes.append(row)
   if z.GetNetCode()!=via.GetNetCode()and poly.Collide(shape,200000):foreign.append(dict(row,kind='ZONE_FILLED_POLYGON'))
 process=fab.local_pofv_via_decision(b,via);guard={};clear=fr._via_spot_clear(b,via.GetPosition(),via.GetWidth(via.TopLayer()),200000,{via.GetNetCode()},drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),existing_via_uuid=uid,foreign_cache={},report=guard)
 return dict(at_nm=list(via.GetPosition()),native_direct_nonplane_contacts=direct,native_filled_zone_contacts=planes,unknown_saved_zone_geometry=unknown,actual_foreign_copper_within_200000nm=foreign,local_process=process,all_layer_guard_clear=clear,all_layer_guard=guard,hole_to_hole_clear=cells._hole_to_hole_clear(b,via.GetPosition(),via.GetDrillValue()/1e6,ignore_via_uuids=(uid,))[0])
old=inventory();via.SetPosition(p.VECTOR2I(*target));new=inventory();oldkeys={(q['uuid'],q['layer'])for q in old['native_direct_nonplane_contacts']};newkeys={(q['uuid'],q['layer'])for q in new['native_direct_nonplane_contacts']};lost=[q for q in old['native_direct_nonplane_contacts']if(q['uuid'],q['layer'])not in newkeys];g=[dict(uuid=force._uid(g),name=g.GetName(),locked=g.IsLocked())for g in b.Groups()if g.ContainsItem(via)]
out=dict(schema=1,source_path=str(source.relative_to(ROOT)),source_sha256=sha,via_uuid=uid,net=via.GetNetname(),source_center_nm=list(origin),proposed_center_nm=list(target),delta_nm=[target[0]-origin[0],target[1]-origin[1]],diameter_nm=via.GetWidth(via.TopLayer()),drill_nm=via.GetDrillValue(),native_layer_stack=[b.GetLayerName(l)for l in layers],padstack_preserved=True,locked=via.IsLocked(),groups=g,group_or_lock_not_motion_permission=True,source=old,destination=new,lost_original_nonplane_contacts=lost,source_pad_uuid=force._uid(pad),source_pad_center_unchanged_nm=list(pad.GetPosition()),required_cut_obligations=[q['uuid']for q in lost if q['kind']=='PCB_TRACK'],saved_fill_refill_and_whole_native_receiving_pending=True,new_holes=0,board_saved=False,current_authority=False,release_authority=False)
assert force._hash(source)==sha
(folder/'C54-source-barrel-repair.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
