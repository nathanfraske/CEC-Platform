import sys,json
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_assembly_envelope as assembly
import cec_fab_profile as fab
from shapely.affinity import translate
p,_=_native();source=ROOT/'experiments/busbars/coherent-mux-20261106/port-repaired-v1/candidate/board.kicad_pcb';b=p.LoadBoard(str(source));fps={f.GetReference():f for f in b.GetFootprints()};refs={'U6','C9','C27','C54','R54'}
v=next(t for t in b.GetTracks()if force._uid(t)=='29c6dd22-a1da-4ce9-9a58-b645a9a40da0')
origin=tuple(v.GetPosition());peer=p.LoadBoard(str(ROOT/'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb'));contract=json.loads((ROOT/'beta/assembly/hub-atx-stack.json').read_text());trials=[]
for dx,dy in [(2,0)]:
 collisions=[]
 for ref in sorted(refs):
  shape=translate(assembly.footprint_planar_envelope(fps[ref])[0],dx,dy)
  for other,fp in fps.items():
   if other in refs or fp.GetLayer()!=fps[ref].GetLayer():continue
   try:poly=assembly.footprint_planar_envelope(fp)[0]
   except ValueError:continue
   if shape.intersects(poly):collisions.append([ref,other])
 paired=assembly.native_translation_check(b,peer,contract,{r:(dx,dy)for r in refs},timeout_s=2.)
 for ref in refs:fps[ref].Move(p.VECTOR2I_MM(dx,dy))
 try:
  at=p.VECTOR2I(origin[0]+round(dx*1e6),origin[1]+round(dy*1e6));block,records=fab.via_at_pad_conflicts(b,at,v.GetWidth(v.TopLayer()),v.GetDrillValue(),v.GetNetCode())
  trials.append(dict(delta_mm=[dx,dy],courtyard_conflicts=collisions,paired_ok=paired['ok'],paired_violations=paired.get('violations'),PR1_barrel_destination_mm=[at.x/1e6,at.y/1e6],PR1_destination_pad_conflicts=records,PR1_destination_pad_blocked=block is not None,all_copper_transport_and_boundaries_unverified=True))
 finally:
  for ref in refs:fps[ref].Move(p.VECTOR2I_MM(-dx,-dy))
r=dict(source_sha256=force._hash(source),barrel_uuid=force._uid(v),barrel_net=v.GetNetname(),barrel_source_mm=[x/1e6 for x in origin],sourceowner='U6.6 PR1 monitor',stationary_monitor_resistors=['R57','R58'],trials=trials,board_saved=False,accepted=False)
(Path(__file__).parent/'repaired-mux-pose-plus2.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
