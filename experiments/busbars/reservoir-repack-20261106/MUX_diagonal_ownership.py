"""Classify one literal native power segment; no mutation or cut authority."""
import sys,json,time,collections
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_source_linear_power_stage as linear
import cec_device_power_roles as roles
import cec_force_current as force
p,_=_native();folder=Path(__file__).parent;study=json.loads((folder/'geometry-map-derived-seven.json').read_text());source=ROOT/study['source'];b=p.LoadBoard(str(source));assert force._hash(source)==study['source_sha256'];uid='25bba609-ee8a-4547-9df7-c906cfc0979c';track=next(t for t in b.GetTracks()if force._uid(t)==uid);net=track.GetNetname();code=track.GetNetCode();items=[t for t in b.GetTracks()if t.GetNetCode()==code]+[q for f in b.GetFootprints()for q in f.Pads()if q.GetNetCode()==code];layers=list(b.GetEnabledLayers().CuStack())
def describe(t):
 row=dict(uuid=force._uid(t),kind=t.GetClass(),net=t.GetNetname())
 if t.GetClass()=='PAD':row.update(ref=t.GetParentFootprint().GetReference(),pin=t.GetNumber(),position_nm=list(t.GetPosition()))
 else:row.update(layer=t.GetLayerName(),start_nm=list(t.GetStart()),end_nm=list(t.GetEnd()),locked=t.IsLocked(),width_nm=t.GetWidth()if t.GetClass()=='PCB_TRACK'else t.GetWidth(t.TopLayer()))
 return row
graph={force._uid(t):[]for t in items};index={force._uid(t):t for t in items}
for i,a in enumerate(items):
 for z in items[i+1:]:
  if any(a.IsOnLayer(l)and z.IsOnLayer(l)and a.GetEffectiveShape(l).Collide(z.GetEffectiveShape(l),0)for l in layers):graph[force._uid(a)].append(force._uid(z));graph[force._uid(z)].append(force._uid(a))
queue=collections.deque([uid]);prev={uid:None}
while queue:
 a=queue.popleft()
 for z in graph[a]:
  if z not in prev:prev[z]=a;queue.append(z)
paths=[]
for t in items:
 if t.GetClass()!='PAD'or force._uid(t)not in prev:continue
 path=[];cursor=force._uid(t)
 while cursor is not None:path.append(describe(index[cursor]));cursor=prev[cursor]
 paths.append(dict(terminal=describe(t),native_explicit_path_from_segment=list(reversed(path))))
zones=[]
for z in b.Zones():
 if z.GetIsRuleArea():continue
 for l in layers:
  if track.IsOnLayer(l)and z.IsOnLayer(l)and z.IsFilled()and z.HasFilledPolysForLayer(l)and z.GetFilledPolysList(l).Collide(track.GetEffectiveShape(l),0):zones.append(dict(uuid=force._uid(z),net=z.GetNetname(),layer=b.GetLayerName(l)))
poses={r:[q[0]/1e6,q[1]/1e6,q[2]]for r,q in study['proposed_poses'].items()};fresh=linear.collect(b,poses,board_hint='atx-24pin-rev3',enabled=True,timeout_s=8.)
out=dict(source=study['source'],source_sha256=study['source_sha256'],segment=describe(track),direct_native_contacts=[describe(index[q])for q in graph[uid]],actual_filled_zone_contacts=zones,explicit_native_terminal_paths=paths,source_manufacturer_pin_roles=roles.footprint_contract(b.FindFootprintByReference('U6')),fresh_source_linear_stage=fresh,groups=[dict(uuid=force._uid(g),name=g.GetName(),locked=g.IsLocked())for g in b.Groups()if g.ContainsItem(track)],scope='Actual source topology and fresh manufacturer/current role. No new ownership waiver: linear stage identifies an output/current domain but explicitly grants no source-trace retirement. Exact cut-boundary reconstruction and saved receiving remain required.',board_saved=False,source_cut_authority=False,release_authority=False)
assert force._hash(source)==study['source_sha256'];(folder/'MUX-diagonal-ownership.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(direct=out['direct_native_contacts'],terminals=[q['terminal']for q in paths],stage_keys=list(fresh),role_keys=list(fresh['U6'])if'U6'in fresh else[]),indent=2))
