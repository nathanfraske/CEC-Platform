"""Read-only independent native terminal/placement/process receiving."""
import json,time
from pathlib import Path
from cec_pipeline.native import _native
p,quiet=_native()
import cec_native_partition_pair as part,cec_force_current as f
import cec_assembly_envelope as en,cec_additive_route_receiving as syntax
ROOT=Path('/home/codex/src/CEC-Platform')
S=ROOT/'experiments/repack/j3-inward-20261105/typed-v10/carrier/board.kicad_pcb'
T=ROOT/'experiments/repack/atx-small-cell-20261105/native-v5/carrier/board.kicad_pcb'
H=ROOT/'experiments/repack/hub-kvm-20261105/native-v15/cover/board.kicad_pcb'
a=p.LoadBoard(str(S));b=p.LoadBoard(str(T));h=p.LoadBoard(str(H))
deadline=time.monotonic()+10;bound=dict(items=16384,vertices=200000,polygons=4096)
old=part._inventory(a,deadline,bound);new=part._inventory(b,deadline,bound)
def pads(board):return {(f._uid(fp),f._uid(q),q.GetNumber()):q for fp in board.GetFootprints()for q in fp.Pads()if q.GetNetCode()>0}
l,r=pads(a),pads(b);assert l.keys()==r.keys();reb={};m=[]
for k,q in l.items():
 z=r[k];assert q.GetNetname()==z.GetNetname()and q.GetShape()==z.GetShape()and tuple(q.GetSize())==tuple(z.GetSize())and tuple(q.GetDrillSize())==tuple(z.GetDrillSize())and tuple(q.GetLayerSet().CuStack())==tuple(z.GetLayerSet().CuStack())
 reb[f._item_key(z)]=f._item_key(q)
 if tuple(q.GetPosition())!=tuple(z.GetPosition()):m.append(dict(reference=q.GetParentFootprint().GetReference(),number=q.GetNumber(),source_nm=list(q.GetPosition()),candidate_nm=list(z.GetPosition())))
o={};n={}
for q in l.values():o.setdefault(old['component_of'][f._item_key(q)],set()).add(f._item_key(q))
for q in r.values():n.setdefault(new['component_of'][f._item_key(q)],set()).add(reb[f._item_key(q)])
dem=[v for v in o.values()if not any(v<=w for w in n.values())]
def courts(board):
 fs=list(board.GetFootprints());out=[]
 for i,x in enumerate(fs):
  for y in fs[i+1:]:
   if x.GetLayer()!=y.GetLayer():continue
   q=x.GetCourtyard(x.GetLayer()).CloneDropTriangulation();q.BooleanIntersection(y.GetCourtyard(y.GetLayer()))
   if q.OutlineCount():out.append(tuple(sorted([x.GetReference(),y.GetReference()])))
 return set(out)
cold,cnew=courts(a),courts(b)
contract=json.loads((ROOT/'beta/assembly/hub-atx-stack.json').read_text());stack,data=en.evaluate_boards(b,h,contract)
_,oldast=syntax._nodes(S);_,newast=syntax._nodes(T)
typed={f._uid(t)for g in a.Groups()if g.GetName().startswith('CEC_LOCAL_SUPPLY_ALLOCATION_V1|')for t in g.GetItems()}
assert all(oldast[u]==newast[u]for u in typed)
records=json.loads((T.parents[1]/'additions.json').read_text())['operations']
def process(node):return [v for v in node if not(isinstance(v,list)and str(v[0])in('uuid','at','net'))]
vias=[v for v in records if v['operation']=='explicit_pad_owned_ordinary_control_via']
assert all(process(oldast[v['process_prototype_uuid']])==process(newast[v['uuid']])for v in vias)
report=T.parents[1]/'carrier-drc.json';drc=json.loads(report.read_text())
result=dict(source=dict(path=str(S),sha256=f._hash(S)),candidate=dict(path=str(T),sha256=f._hash(T)),cover=dict(path=str(H),sha256=f._hash(H)),native_DRC=dict(errors=sum(v['severity']=='error'for v in drc['violations']),opens=len(drc['unconnected_items']),report=str(report),sha256=f._hash(report)),original_terminal_partition=dict(preserved=not dem,source_terminal_count=len(l),source_components=len(o),candidate_components=len(n),demoted_components=dem,moved_pad_rebindings=m,new_vias_are_not_original_terminals=True,method='Native CONNECTIVITY_DATA, real native copper and decomposed saved-fill islands, original pad identity rebindings. Not endpoint graphs or whole-zone UUIDs.',retained_copper_partition_or_current_qualification=False),sameface_native_courtyards=dict(source_intersections=sorted(cold),candidate_intersections=sorted(cnew),new_intersections=sorted(cnew-cold)),paired_native_assembly=dict(ok=stack['ok'],missing=stack['missing'],check_count=len(stack['checks']),failed=[v for v in stack['checks']if not v['ok']],minimum_margin_mm=min(v['margin_mm']for v in stack['checks']if 'margin_mm'in v)),typed_allocated_member_AST=dict(count=len(typed),all_unchanged=True),new_pad_owned_via_process_AST=dict(count=len(vias),all_source_process_fields_exact_except_uuid_at_net=True,operations=vias),routing_admitted=False,current_thermal_qualified=False,release_authority=False)
print('RESULT'+json.dumps(result,default=lambda v:sorted(v,key=repr)if isinstance(v,set)else str(v)))
