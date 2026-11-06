"""Private, bounded exact-prototype via geometry experiment; no admission."""
import sys,json,uuid
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform')
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
import cec_force_current as f
import cec_additive_route_receiving as syntax
import cec_source_literal_additions as literal
SOURCE=ROOT/'experiments/repack/bar-land-20261105/carrier/board.kicad_pcb'
WORK=ROOT/'experiments/repack/via-array-review-20261105'
EXPECTED='c9cac71adb685a7f32e48af34793455927f89f9207c2af1b54577a4f95a15251'
assert f._hash(SOURCE)==EXPECTED
TARGET=WORK/'trial/board.kicad_pcb'
mode=sys.argv[1]
if mode in ('scan','blockers'):
 b=pcbnew.LoadBoard(str(SOURCE));p=next(t for t in b.GetTracks() if f._uid(t)=='505280f0-f8c4-47a2-962c-0438b631e8cf')
 items=[*b.GetTracks(),*(p for fp in b.GetFootprints() for p in fp.Pads())]
 rows=[]
 for yi in ([554,566,600,650] if mode=='blockers' else range(547,745,4)):
  y=yi/10;legal=[]
  for x in ([67.8,69.,70.2] if mode=='blockers' else [67.65,70.35]):
   p.SetPosition(pcbnew.VECTOR2I(round(x*1e6),round(y*1e6)))
   blocked=False
   for item in items:
    if item.GetNetname()==p.GetNetname():continue
    for layer in (0,2,4,6,8,10):
     if item.IsOnLayer(layer) and p.GetEffectiveShape(layer).Collide(item.GetEffectiveShape(layer),250000):
      blocked=True
      if mode=='blockers':print(json.dumps(dict(at=[x,y],uuid=f._uid(item),net=item.GetNetname(),layer=b.GetLayerName(layer),kind=item.GetClass(),start=list(item.GetStart()) if item.GetClass()=='PCB_TRACK' else list(item.GetPosition()),end=list(item.GetEnd()) if item.GetClass()=='PCB_TRACK' else None,width=item.GetWidth(layer) if item.GetClass()=='PCB_VIA' else item.GetWidth() if item.GetClass()=='PCB_TRACK' else None)))
      break
    if blocked:break
   if not blocked:legal.append(x)
  if len(legal)==2:rows.append([y,legal])
 print(json.dumps(rows));sys.exit()
if mode=='construct':
 if not TARGET.exists():TARGET=f._copy_family(SOURCE,WORK/'trial')
 assert f._hash(TARGET)==EXPECTED
 b=pcbnew.LoadBoard(str(SOURCE))
 prototype=next(t for t in b.GetTracks() if f._uid(t)=='505280f0-f8c4-47a2-962c-0438b631e8cf')
 assert prototype.GetParentGroup() is None and prototype.GetWidth()==900000 and prototype.GetDrillValue()==500000
 rows=[]
 for y in (55.4,56.6,70.8,72.0):
  for x in (67.8,69.,70.2):
   via=prototype.Duplicate();via.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,EXPECTED+f':via:{x}:{y}'))))
   via.SetPosition(pcbnew.VECTOR2I(round(x*1e6),round(y*1e6)));b.Add(via)
   rows.append(dict(uuid=f._uid(via),position_mm=[x,y]))
 import cec_zone_fill as fill,cec_field_coupling as field
 zones=pcbnew.ZONES()
 for z in b.Zones():
  if not z.GetIsRuleArea():zones.append(z)
 fill.compile_selected(b,zones,timeout_s=10.,initialize_selected=True)
 raw=WORK/'native.kicad_pcb';field._save_field_snapshot(b,raw)
 # Append only literal new vias, then replace saved native zone fills, retaining
 # source project metadata and every preexisting non-zone object exactly.
 text=literal.assemble(SOURCE.read_text(),raw.read_text(),ground_ids=[f._uid(z) for z in b.Zones() if z.GetNetname()=='GND'])
 TARGET.write_text(text)
 root,old=syntax._nodes(TARGET);_,new=syntax._nodes(raw)
 zoneids={f._uid(z) for z in b.Zones() if not z.GetIsRuleArea()}
 lookup={id(n):k for k,n in old.items()}
 root[1:]=[new[lookup[id(n)]] if lookup.get(id(n)) in zoneids else n for n in root[1:]]
 TARGET.write_text(syntax._render(root)+'\n')
 (WORK/'placements.json').write_text(json.dumps(dict(source_sha256=EXPECTED,prototype_uuid=f._uid(prototype),diameter_mm=.9,drill_mm=.5,grouped=False,placements=rows,trial_sha256=f._hash(TARGET)),indent=2)+'\n')
 print(f._hash(TARGET))
elif mode=='drc':
 import cec_native_drc_runner as drc
 print(json.dumps(drc.run(TARGET,WORK/'drc.json',reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',timeout_s=10.,footprint_table=ROOT/'checkpoints/review-20261105-outline-compaction/boards/atx-24pin-rev3/library/fp-lib-table')))
else:raise ValueError(mode)
assert f._hash(SOURCE)==EXPECTED
