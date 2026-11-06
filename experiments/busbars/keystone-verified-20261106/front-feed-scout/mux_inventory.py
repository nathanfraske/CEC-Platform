import sys,json
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
p,_=_native();source=ROOT/'experiments/busbars/part-model-20261106/endpoint-first-20261106/vbus-shortcut-v6/candidate/board.kicad_pcb';b=p.LoadBoard(str(source));fps={fp.GetReference():fp for fp in b.GetFootprints()};tracks=list(b.GetTracks());nets={q.GetNetname()for q in fps['U6'].Pads()};refs={'U6','C9','C27','R54','C54','C55','C51'}
def tr(t):
 return dict(uuid=force._uid(t),kind=t.GetClass(),net=t.GetNetname(),layer=t.GetLayerName(),start_mm=[t.GetStart().x/1e6,t.GetStart().y/1e6],end_mm=[t.GetEnd().x/1e6,t.GetEnd().y/1e6],width_nm=t.GetWidth()if t.GetClass()=='PCB_TRACK'else None,locked=t.IsLocked(),layers=list(t.GetLayerSet().CuStack())if t.GetClass()=='PCB_VIA'else[t.GetLayer()])
inventory={}
for net in sorted(nets):
 pads=[dict(ref=fp.GetReference(),pin=q.GetNumber(),value=fp.GetValue(),xy_mm=[q.GetPosition().x/1e6,q.GetPosition().y/1e6])for fp in b.GetFootprints()for q in fp.Pads()if q.GetNetname()==net]
 inventory[net]=dict(pads=pads,tracks=[tr(t)for t in tracks if t.GetNetname()==net]if net not in {'GND','+5VSB'}else[])
ground=[]
for ref in refs:
 for pad in fps[ref].Pads():
  if pad.GetNetname()!='GND':continue
  hits=[]
  for t in tracks:
   if t.GetNetname()!='GND':continue
   for layer in pad.GetLayerSet().CuStack():
    if (t.GetClass()=='PCB_VIA'and layer in t.GetLayerSet().CuStack()or t.GetLayer()==layer)and t.GetEffectiveShape(layer).Collide(pad.GetEffectiveShape(layer),0):hits.append(tr(t));break
  ground.append(dict(ref=ref,pin=pad.GetNumber(),native_direct_contacts=hits,ownership_scope='Direct native contact only; sharedground via/chain ownership must be independently derived'))
r=dict(source_sha256=force._hash(source),nets=inventory,ground_pad_direct_contacts=ground,existing_seven_part_scope=sorted(refs),unposed_monitor_dividers=['R55','R56','R57','R58'],external_output_participants=['C21','C20','U5'],coherent_scope_note='C51 SS capacitor already included; C9 VBUS bypass,C27 outputbypass,C54/C55 standbybypass included. Monitor divider sourceanchors R55/R57 at+5VSB and returns R56/R58 remain remote; must reconnect exact U6_OV1/PR1 boundaries or explicitly expand cell. Do not move U5/C20/C21 implicitly.',usefulness='Moving full return and ILM barrel population+4X can vacate original B.Cu blockers atx11.245..13.86,y45.86..49.135. Existing sourcecompiler does not yet prove that ownership; original+4Xbody/stackpass alone insufficient. C55.GND proposedposition(24.4,48)conflicts external5V_SYS_PORT track; external corridor reroute required even after internaltransport.',board_saved=False,accepted=False)
(Path(__file__).parent/'mux-inventory.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(source_sha256=r['source_sha256'],private_participants={n:sorted({q['ref']for q in v['pads']})for n,v in inventory.items()if 'U6_'in n},ground=ground),indent=2))
