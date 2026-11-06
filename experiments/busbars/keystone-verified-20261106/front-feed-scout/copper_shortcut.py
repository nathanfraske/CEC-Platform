import sys,json,hashlib,time
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_fr as fr
from cec_pipeline import path_probe
p,_=_native();source=ROOT/'experiments/busbars/part-model-20261106/endpoint-first-20261106/vbus-shortcut-v6/candidate/board.kicad_pcb'
sha='4b7457bd28a1a798b6c851b354a2807d02472b8c85b6f583ec48833dce616310';assert force._hash(source)==sha
b=p.LoadBoard(str(source));owned={'e8ae802e-223d-4792-aa23-8e06299434b5','3ace9012-8691-4de3-be94-98946715204b','5c1c6766-9a73-43fb-8528-378ff7ca4890','278bc5d9-6b20-4816-9ccb-85960582aaed'};held=list(b.GetTracks());removed=[]
for t in held:
 if force._uid(t) in owned:
  assert t.GetNetname()=='/SENSE3V3_HI' and t.GetLayer()==p.B_Cu and t.GetWidth()==6535523
  removed.append(dict(uuid=force._uid(t),start=[t.GetStart().x/1e6,t.GetStart().y/1e6],end=[t.GetEnd().x/1e6,t.GetEnd().y/1e6],width_nm=t.GetWidth()));b.Remove(t)
assert len(removed)==4
poses=[(9.2,52.8),(9.2,45.5),(13.15,41.55),(18.35,41.55)];segments=[]
for a,z in zip(poses,poses[1:]):
 u,v=p.VECTOR2I_MM(*a),p.VECTOR2I_MM(*z)
 hits=force._native_track_rule_hits(b,p.SHAPE_SEGMENT(u,v,6535523),p.B_Cu)
 clear=fr._tap_foreign_clear(b,u,v,6535523,p.B_Cu,200000,{b.GetNetcodeFromNetname('/SENSE3V3_HI')})
 blockers=[]
 for item in list(b.GetTracks())+[pad for fp in b.GetFootprints() for pad in fp.Pads()]:
  if item.GetNetname()=='/SENSE3V3_HI':continue
  if item.GetClass()=='PAD':
   if p.B_Cu not in item.GetLayerSet().CuStack():continue
  elif item.GetClass()=='PCB_VIA':
   if p.B_Cu not in item.GetLayerSet().CuStack():continue
  elif item.GetLayer()!=p.B_Cu:continue
  if item.GetEffectiveShape(p.B_Cu).Collide(p.SHAPE_SEGMENT(u,v,6535523),200000):
   blockers.append(dict(uuid=force._uid(item),kind=item.GetClass(),net=item.GetNetname(),at=[item.GetPosition().x/1e6,item.GetPosition().y/1e6]))
 segments.append(dict(start=a,end=z,native_rule_hits=hits,edge_clear=fr._edge_leg_clear(b,u,v,6535523//2),foreign_clear=clear,concrete_copper_blockers=blockers))
r=dict(source_sha256=sha,replaced_owned_chain=removed,proposed_segments=segments,width_nm=6535523,clearance_nm=200000,ram_removal_only=True,board_saved=False,scope='One exact straight/45-degree copper-only shortcut; full foreign-copper check added after initial rule-only report; not final DRC or global no-path proof',original_lower_chain_boundary_mm=[7.472648,52.8],boundary_restored=False,boundary_note='Proposed x9.2 joins retained lower same-net track endpoint, not exact removed-chain x7.472648 endpoint. Exact endpoint replay or explicit co-owned stub removal required; not accepted topology.',nominal_12v_x4_right_edge_mm=4+3.230592/2,nominal_3v3_x9_2_left_edge_mm=9.2-6.535523/2,nominal_parallel_gap_mm=9.2-6.535523/2-(4+3.230592/2),trim_qualified=False)
r['exact_boundary_connector']=dict(start=[7.472648,52.8],end=[9.2,52.8],width_nm=6535523,foreign_clear=fr._tap_foreign_clear(b,p.VECTOR2I_MM(7.472648,52.8),p.VECTOR2I_MM(9.2,52.8),6535523,p.B_Cu,200000,{b.GetNetcodeFromNetname('/SENSE3V3_HI')}),left_edge_mm=7.472648-6.535523/2,nominal_gap_to_relocated_x4_12v_mm=(7.472648-6.535523/2)-(4+3.230592/2),decision='Exact boundary connector retains a leftward endcap incompatible with straight x4 12V; co-owned chain boundary must change instead, and main shortcut independently fails foreign-copper screen.')
r['shared_all_guards_probe']=path_probe.inspect(b,net='/SENSE3V3_HI',layer='B.Cu',
 width_nm=6535523,clearance_nm=200000,points_nm=[[round(x*1e6),round(y*1e6)]for x,y in poses])
assert not r['shared_all_guards_probe']['geometry_screen_clear']
assert force._hash(source)==sha
(Path(__file__).parent/'copper-shortcut.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
