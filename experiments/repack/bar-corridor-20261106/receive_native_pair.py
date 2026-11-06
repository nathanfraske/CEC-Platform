"""Read-only independent saved explicit-native-macro receiving."""
import argparse,json
from pathlib import Path
from cec_pipeline.native import _native
p,_=_native()
from cec_pipeline import cells
import cec_current_debt as current,cec_native_drc_runner as drc
import cec_additive_route_receiving as syntax
import cec_native_partition_pair as partitions,cec_cell_macro_requests as compiler
import cec_complete_cell_receiving as cell
ap=argparse.ArgumentParser();ap.add_argument('folder');args=ap.parse_args();R=Path(args.folder).resolve();plan=json.loads((R/'route-plan.json').read_text());B=Path(plan.get('candidate',str(R/'board.kicad_pcb')));S=Path(plan['source']);op=plan['operation'];record=json.loads((R/'construction.json').read_text())['changes'][0];out={}
def save(name,call):
 try:out[name]=call()
 except Exception as e:out[name]={'ok':False,'error':str(e)}
 (R/'independent-receiving.json').write_text(json.dumps(out,indent=2,default=str)+'\n');print(name,json.dumps(out[name],default=str)[:1200],flush=True)
save('macro',lambda:cells.receive_macro(S,B,op,record,'atx-24pin-rev3'))
save('current',lambda:current.receive(S,B,board_hint='atx-24pin-rev3'))
save('native_drc',lambda:drc.run(B,R/'native-drc.json',reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',timeout_s=10.,footprint_table='checkpoints/review-20261105-outline-compaction/boards/atx-24pin-rev3/library/fp-lib-table'))
if (R/'native-drc.json').exists():
 x=json.loads((R/'native-drc.json').read_text());out['native_counts']=dict(errors=sum(v.get('severity')=='error'for v in x['violations']),warnings=sum(v.get('severity')=='warning'for v in x['violations']),opens=len(x['unconnected_items']))
a,b=syntax._nodes(S)[1],syntax._nodes(B)[1];out['changed_source_zones']=[u for u,n in a.items()if n[0]=='zone'and n!=b.get(u)]
old,new=p.LoadBoard(str(S)),p.LoadBoard(str(B))
bindings=compiler.identity_rebindings(old,new,record['native_macro_packet'],timeout_s=10.)
rebindings=cell._pad_rebindings(old,new,record['native_macro_packet']['source_plan']['poses'])
assert not any(k[0]!='pad'and k!=v for k,v in bindings.items())
assert not any(rebindings.get(k)!=v for k,v in bindings.items()if k[0]=='pad')
save('partitions',lambda:partitions.compare(old,new,timeout_s=10.,identity_rebindings=rebindings,retired_uuids=record['retired_track_uuids']))
print(json.dumps({k:out[k]for k in('native_counts','changed_source_zones')if k in out}),flush=True)
