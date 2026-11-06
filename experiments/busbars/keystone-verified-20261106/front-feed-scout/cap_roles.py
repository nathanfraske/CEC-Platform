import sys,json
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_constraints as c
import cec_force_current as force
import cec_additional_aggregate_macro as aggregate
import cec_device_bypass as db
from cec_footprint_fields import footprint_properties
p,_=_native();source=ROOT/'experiments/busbars/part-model-20261106/endpoint-first-20261106/vbus-shortcut-v6/candidate/board.kicad_pcb';b=p.LoadBoard(str(source));fps={q.GetReference():q for q in b.GetFootprints()}
with force._thermal_hint('atx-24pin-rev3'):a=c._device_bypass_assignment(b,project_max_mm=3.5)
selected={v['cap_ref']for v in a['assigned'].values()};roles=[]
for ref in ['C9','C27','C54','C55','C51']:
 fp=fps[ref];rail=next(q.GetNetname()for q in fp.Pads()if q.GetNetname()!='GND');reqs=[q for q in a['requirements']if q['rail']==rail and q.get('return_rail','GND')=='GND'];roles.append(dict(ref=ref,rail=rail,selected=ref in selected,selected_assignments=[v['requirement']for v in a['assigned'].values()if v['cap_ref']==ref],declared_owner=db.declared_owner(footprint_properties(fp)),rail_requirement_owners=sorted({(q['ref'],str(q['pin']))for q in reqs})))
collect_checks=[]
for ref in ['C51','C55']:
 poses={r:[fps[r].GetPosition().x/1e6+4,fps[r].GetPosition().y/1e6,fps[r].GetOrientationDegrees()]for r in ['U6',ref]}
 try:
  result=aggregate.collect(b,poses,board_hint='atx-24pin-rev3',timeout_s=3.)
  collect_checks.append(dict(cap=ref,ok=True,owners=list(result)))
 except ValueError as e:collect_checks.append(dict(cap=ref,ok=False,error=str(e)))
r=dict(source_sha256=force._hash(source),roles=roles,collect_checks=collect_checks,source_unchanged=True)
out=Path(__file__).parent/'cap-roles.json';out.write_text(json.dumps(r,indent=2,default=str)+'\n');print(json.dumps(r,indent=2,default=str))
