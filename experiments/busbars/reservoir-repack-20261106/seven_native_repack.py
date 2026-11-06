"""One requested seven-part repack, all source copper retained in RAM."""
import sys,json,math
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_assembly_envelope as assembly
import cec_fab_profile as fab
import cec_decoupler_cell as cells
import cec_fr as fr
p,_=_native();folder=Path(__file__).parent;source=ROOT/'experiments/busbars/cap-ground-repair-20261106/candidate/board.kicad_pcb';sha=force._hash(source);assert sha.startswith('1512d4f');b=p.LoadBoard(str(source));fps={f.GetReference():f for f in b.GetFootprints()};poses={r:[fps[r].GetPosition().x+2000000,fps[r].GetPosition().y,fps[r].GetOrientationDegrees()]for r in ['U6','C9','C27','R54']};poses.update(C55=[19750000,48004594,270],C54=[17500000,45300000,90],C51=[17725000,50900000,270]);orig={r:[*list(fps[r].GetPosition()),fps[r].GetOrientationDegrees()]for r in poses}
bottom='--bottom-row'in sys.argv
if bottom:poses.update(C54=[17000000,49000000,180],C51=[17725000,51025000,270])
for ref,target in poses.items():fps[ref].SetOrientationDegrees(target[2]);fps[ref].SetPosition(p.VECTOR2I(target[0],target[1]))
shapes={}
for ref,fp in fps.items():
 try:shapes[ref]=assembly.footprint_planar_envelope(fp)[0]
 except ValueError:pass
coll=[];seen=set()
for ref in poses:
 for other,shape in shapes.items():
  key=tuple(sorted((ref,other)))
  if other==ref or key in seen or fps[ref].GetLayer()!=fps[other].GetLayer():continue
  seen.add(key);intersection=shapes[ref].intersection(shape)
  if not intersection.is_empty:coll.append(dict(refs=key,area_mm2=intersection.area,bounds=[list(shapes[ref].bounds),list(shape.bounds)],other_owner_moved=other in poses))
peer=ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb';stack=ROOT/'beta/assembly/hub-atx-stack.json';paired,_=assembly.evaluate_boards(b,p.LoadBoard(str(peer)),json.loads(stack.read_text()));ground=next(q for q in fps['C55'].Pads()if q.GetNumber()=='2');width=max(200000,int(b.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(b,'GND')['width']));face=p.F_Cu
class GroundView:
 def GetTracks(self):return[t for t in b.GetTracks()if t.GetNetname()=='GND'and(t.GetClass()=='PCB_VIA'or t.GetClass()in('PCB_TRACK','PCB_ARC')and int(t.GetLayer())==face and t.GetWidth()>=width)]
 def __getattr__(self,name):return getattr(b,name)
immediate=cells._existing_return(GroundView(),ground,.8,allow_native_track_body=True);immediate_result=None
if immediate is not None:
 cost,v=immediate;blocked,records=fab.via_at_pad_conflicts(b,v.GetPosition(),v.GetWidth(v.TopLayer()),v.GetDrillValue(),v.GetNetCode());immediate_result=dict(distance_mm=cost,via_uuid=force._uid(v),process_pad_blocked=blocked is not None,records=records)
via=next(t for t in b.GetTracks()if force._uid(t)=='c25714c1-f2d8-4e0e-9711-7d208ce1da97');g54=next(q for q in fps['C54'].Pads()if q.GetNumber()=='2');original_axis=list(via.GetPosition());via.SetPosition(g54.GetPosition());report={};spot=fr._via_spot_clear(b,via.GetPosition(),via.GetWidth(via.TopLayer()),200000,{via.GetNetCode()},drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),existing_via_uuid=force._uid(via),foreign_cache={},report=report);foreign=[]
for t in b.GetTracks():
 if t.GetNetCode()==via.GetNetCode():continue
 for layer in b.GetEnabledLayers().CuStack():
  if t.IsOnLayer(layer)and t.GetEffectiveShape(layer).Collide(via.GetEffectiveShape(layer),200000):foreign.append(dict(uuid=force._uid(t),net=t.GetNetname(),layer=b.GetLayerName(layer),kind=t.GetClass(),start_nm=list(t.GetStart()),end_nm=list(t.GetEnd()),width_nm=t.GetWidth()if t.GetClass()=='PCB_TRACK'else t.GetWidth(t.TopLayer())))
owner=next(q for q in fps['U6'].Pads()if q.GetNumber()=='7');sup=next(q for q in fps['C55'].Pads()if q.GetNumber()=='1');supp54=next(q for q in fps['C54'].Pads()if q.GetNumber()=='1')
out=dict(source=str(source.relative_to(ROOT)),source_sha256=sha,peer_sha256=force._hash(peer),stack_sha256=force._hash(stack),source_poses=orig,proposed_poses=poses,proposed_pads={r:[dict(pin=q.GetNumber(),net=q.GetNetname(),at_nm=list(q.GetPosition()))for q in fps[r].Pads()]for r in poses},courtyard_collisions=coll,paired_ok=paired['ok'],paired_violations=paired['violations'],C55_exact_point8_Ground_observation=immediate_result,C54_original_axis_nm=original_axis,C54_proposed_axis_nm=list(via.GetPosition()),C54_barrel_geometry_nm=[via.GetWidth(via.TopLayer()),via.GetDrillValue()],C54_source_pad_process=fab.local_pofv_via_decision(b,via),C54_all_layer_spot_clear=spot,C54_all_layer_guard=report,C54_actual_foreign_track_conflicts=foreign,owner_IN1_pad_uuid=force._uid(owner),direct_owner_to_C55_centers_mm=math.dist(tuple(owner.GetPosition()),tuple(sup.GetPosition()))/1e6,via_C54_lower_bound_centers_mm=(math.dist(tuple(owner.GetPosition()),tuple(supp54.GetPosition()))+math.dist(tuple(supp54.GetPosition()),tuple(sup.GetPosition())))/1e6,local_supply_max_mm=3.5,source_copper_retained=True,old_C55_tail_retirement_separate_and_pending=True,board_saved=False,accepted=False,release_authority=False)
from shapely.affinity import affine_transform
hub=p.LoadBoard(str(peer));hub_c37=next(f for f in hub.GetFootprints()if f.GetReference()=='C37');hub_shape=assembly.footprint_planar_envelope(hub_c37)[0]
out['unmoved_Hub_C37']=dict(native_courtyard_bounds_mm=list(hub_shape.bounds),in_ATX_frame_courtyard_bounds_mm=list(affine_transform(hub_shape,[-1,0,0,1,86,9.8]).bounds),native_position_nm=list(hub_c37.GetPosition()),in_ATX_frame_body_center_mm=[86-hub_c37.GetPosition().x/1e6,9.8+hub_c37.GetPosition().y/1e6],C51_native_courtyard_bounds_mm=list(shapes['C51'].bounds),scope='Courtyard bounds for locating obstacle only; paired gate uses declared reservoir body/vent/height model, not this rectangle as substitute')
assert force._hash(source)==sha;(folder/('geometry-seven-bottom-row.json'if bottom else 'geometry-seven-explicit-repack.json')).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k not in('proposed_pads','source_poses','proposed_poses')},indent=2))
