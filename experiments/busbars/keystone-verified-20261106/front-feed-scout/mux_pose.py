import sys,json
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_assembly_envelope as assembly
import cec_force_current as force
from shapely.affinity import translate
p,_=_native();source=ROOT/'experiments/busbars/part-model-20261106/endpoint-first-20261106/vbus-shortcut-v6/candidate/board.kicad_pcb'
b=p.LoadBoard(str(source));peer=p.LoadBoard(str(ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb'));contract=json.loads((ROOT/'beta/assembly/hub-atx-stack.json').read_text())
refs={'U6','C9','C27','R54','C54','C55','C51'};fps={fp.GetReference():fp for fp in b.GetFootprints()};shapes={}
for ref,fp in fps.items():
 try:shapes[ref]=assembly.footprint_planar_envelope(fp)[0]
 except ValueError:pass
trials=[]
for dx,dy in [(4.,0.),(4.,-4.)]:
 collisions=[]
 for ref in refs:
  shape=translate(shapes[ref],dx,dy)
  for other,polygon in shapes.items():
   if other in refs or fps[other].GetLayer()!=fps[ref].GetLayer():continue
   if shape.intersects(polygon):collisions.append(dict(moved=ref,fixed=other,gap_mm=shape.distance(polygon)))
 paired=assembly.native_translation_check(b,peer,contract,{ref:(dx,dy)for ref in refs},timeout_s=2.)
 fixed_copper_hits=[]
 for ref in refs:fps[ref].Move(p.VECTOR2I_MM(dx,dy))
 try:
  for ref in refs:
   for pad in fps[ref].Pads():
    for layer in pad.GetLayerSet().CuStack():
     shape=pad.GetEffectiveShape(layer)
     for item in list(b.GetTracks())+[q for fp in b.GetFootprints() if fp.GetReference() not in refs for q in fp.Pads()]:
      if item.GetNetCode()==pad.GetNetCode():continue
      if item.GetClass() in ('PAD','PCB_VIA'):
       if layer not in item.GetLayerSet().CuStack():continue
      elif item.GetLayer()!=layer:continue
      if item.GetEffectiveShape(layer).Collide(shape,200000):fixed_copper_hits.append(dict(moved=ref,pad=pad.GetNumber(),pad_net=pad.GetNetname(),layer=b.GetLayerName(layer),fixed_uuid=force._uid(item),fixed_kind=item.GetClass(),fixed_net=item.GetNetname()))
 finally:
  for ref in refs:fps[ref].Move(p.VECTOR2I_MM(-dx,-dy))
 trials.append(dict(delta_mm=[dx,dy],courtyard_collisions=collisions,paired=paired,pin_local_relative_placement_preserved=True,fixed_route_moved_pad_copper_conflicts=fixed_copper_hits,copper_trial_not_performed=True,copper_scope='Actual moved pad vs unchanged native pads/tracks/vias all copper layers,0.2mm. Not full cut copper/zone/return reconstruction; old local copper retained as fixed diagnostic obstacles.',accepted=False))
r=dict(source_sha256=force._hash(source),group=sorted(refs),trials=trials,scope='Two deliberate common rigid component translations; no copper ownership or routing admission, no board save',edge=dict(route_center_x_mm=4,width_mm=3.230592,default_guard_mm=.5,max_left_trim_mm=1.884704,center_min_for_2mm_trim=4.115296),next_operation='Compile complete local copper+via ownership and cut before cell translation. Include entire lower 3V3 track97e88707-e4ef-4c30-af4e-724ee6e7d22d so no obsolete x7.472648 endcap remains. Repack contextual cells if courtyard test rejects; recheck complete transformed native copper and rebuilt boundaries, saved peer/stack, bypass and source-current receivers.')
(Path(__file__).parent/'mux-pose.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
