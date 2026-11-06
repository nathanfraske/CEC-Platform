"""Private staged construction; each invocation externally bounded to ten seconds."""
import sys,json,time,shutil,hashlib,argparse
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_control_gate_bias_placement as native
import cec_assembly_envelope as assembly
p,_=_native();folder=Path(__file__).parent;study=json.loads((folder/'C37-coordinated-translation.json').read_text())
source=ROOT/study['peer'];out=folder/'hub-C37-vent-v1';candidate=out/'candidate'/'board.kicad_pcb'
assert force._hash(source)==study['peer_sha256']
parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['construct','refill','literal-save','receive','verify']);args=parser.parse_args()
if args.mode=='construct':
 assert not out.exists(),'private candidate already exists; refusing overwrite'
 candidate.parent.mkdir(parents=True)
 copied={}
 for src in source.parent.glob('board.*'):
  if src.is_file():shutil.copy2(src,candidate.parent/src.name);copied[src.name]=force._hash(src)
 b=p.LoadBoard(str(candidate));fp=b.FindFootprintByReference('C37');fp.SetPosition(p.VECTOR2I(73500000,49700000));p.SaveBoard(str(candidate),b)
 report=dict(source=str(source),source_sha256=force._hash(source),copied_source_family_sha256=copied,candidate_sha256=force._hash(candidate),pose=[73500000,49700000,90],no_copper_edits=True)
elif args.mode=='refill':
 import cec_zone_fill as fill
 b=p.LoadBoard(str(candidate));result=fill.fill_with_report(b);p.SaveBoard(str(candidate),b)
 report=dict(native_refill=result,candidate_sha256=force._hash(candidate),saved=True)
elif args.mode=='literal-save':
 import cec_copper_echo as sexpr
 import cec_additive_route_receiving as additive
 original=sexpr._parse(sexpr._TOKEN.findall(source.read_text()));filled=sexpr._parse(sexpr._TOKEN.findall(candidate.read_text()))
 def uid(node):
  return next((c[1].strip('"')for c in node[1:]if isinstance(c,list)and c and c[0]=='uuid'),None)
 fills={uid(n):[c for c in n[1:]if isinstance(c,list)and c and c[0]in ('filled_polygon','fill_segments')]for n in filled[1:]if isinstance(n,list)and n and n[0]=='zone'}
 for n in original[1:]:
  if not isinstance(n,list)or not n:continue
  if n[0]=='footprint'and uid(n)=='3aee6a4d-c364-461a-8f3c-649ab16f0f3e':
   at=next(c for c in n[1:]if isinstance(c,list)and c and c[0]=='at');at[2]='49.7'
  if n[0]=='zone':
   n[:]=[c for c in n if not isinstance(c,list)or not c or c[0]not in ('filled_polygon','fill_segments')]
   n.extend(fills[uid(n)])
 candidate.write_text(additive._render(original)+'\n')
 report=dict(literal_original_tree_preserved_except_C37_at_and_native_refilled_zone_payloads=True,candidate_sha256=force._hash(candidate))
elif args.mode=='receive':
 import cec_pose_additive_reconstruction as receiving
 b=p.LoadBoard(str(source));fp=b.FindFootprintByReference('C37')
 report=receiving.receive(source,candidate,selected_footprint_uuids=[force._uid(fp)],board_hint='hub-standard-rev2',timeout_s=9.7,max_shift_mm=.1)
 report['actual_board_hint']='hub-standard-rev2'
else:
 import cec_field_coupling as field
 import cec_native_partition_pair as partitions
 a=p.LoadBoard(str(source));b=p.LoadBoard(str(candidate));af={f.GetReference():f for f in a.GetFootprints()};bf={f.GetReference():f for f in b.GetFootprints()}
 sa,_=force._preservation_snapshot(source);sb,_=force._preservation_snapshot(candidate)
 footprint_deltas=[]
 for ref,fp in af.items():
  before=sa[force._uid(fp)];after=sb[force._uid(bf[ref])]
  if before!=after:footprint_deltas.append(dict(ref=ref,before_pose=[*fp.GetPosition(),fp.GetOrientationDegrees()],after_pose=[*bf[ref].GetPosition(),bf[ref].GetOrientationDegrees()]))
 def authored(path):
  import cec_copper_echo as sexpr
  nodes=sexpr._parse(sexpr._TOKEN.findall(Path(path).read_text()));result=[]
  for node in nodes[1:]:
   if not isinstance(node,list)or not node or node[0]not in ('segment','arc','via','zone','group'):continue
   if node[0]=='zone':node=[x for x in node if not isinstance(x,list)or not x or x[0]not in ('filled_polygon','fill_segments','filled_areas_thickness')]
   result.append(sexpr._freeze(node))
  return sorted(result,key=str)
 contacts={}
 for pad in bf['C37'].Pads():
  old=af['C37'].FindPadByNumber(pad.GetNumber());prior=native._direct_contacts(a,old,time.monotonic()+2.);now=native._direct_contacts(b,pad,time.monotonic()+2.)
  contacts[pad.GetNumber()]=dict(source=prior,saved=now,all_source_ids_retained={c['item_uuid']for c in prior}<={c['item_uuid']for c in now})
 atx=p.LoadBoard(str(ROOT/study['source']))
 for ref,pose in study['ATX_poses'].items():
  fp=atx.FindFootprintByReference(ref);fp.SetOrientationDegrees(pose[2]);fp.SetPosition(p.VECTOR2I(*pose[:2]))
 paired,_=assembly.evaluate_boards(atx,b,json.loads((ROOT/'beta/assembly/hub-atx-stack.json').read_text()))
 report=dict(candidate_sha256=force._hash(candidate),literal_footprint_deltas=footprint_deltas,authored_copper_zone_outlines_groups_exact=authored(source)==authored(candidate),
  contact_receiving=contacts,paired_ok=paired['ok'],paired_violations=paired['violations'])
 report['all_original_top_level_native_ids_retained']=set(sa)==set(sb)
 report['all_changed_native_items']=[dict(uuid=uid,kind=sa[uid][0])for uid in sorted(sa)if sa[uid]!=sb[uid]]
 report['only_C37_and_zone_fills_changed']=all(uid=='3aee6a4d-c364-461a-8f3c-649ab16f0f3e'or sa[uid][0]=='zone'for uid in sa if sa[uid]!=sb[uid])
 report['stack_contract_sha256']=force._hash(ROOT/'beta/assembly/hub-atx-stack.json')
 report['stack_contract_exact']=report['stack_contract_sha256']==study['stack_sha256']
 import cec_current_topology as topology
 domains=topology.board_current_domains(a,'hub-standard-rev2');widths=topology.route_width_contracts(a,board_hint='hub-standard-rev2')
 net='/HOLD-UP + 3V3 REGULATOR/+5V_HOLD'
 report['actual_hint_current_lookup']=dict(board_hint='hub-standard-rev2',net=net,source_domain=domains.get(net),source_width_contract=widths.get(net),no_inferred_rating=True)
 import cec_fab_profile as fab
 report['saved_fixed_barrel_pad_process']=[]
 for uid in ('434aa75c-5627-464e-9437-06fb40f2f600','ee3f11eb-6272-4635-b0a8-5ff97b44ce1e'):
  via=next(t for t in b.GetTracks()if force._uid(t)==uid)
  blocked,records=fab.via_at_pad_conflicts(b,via.GetPosition(),via.GetWidth(via.TopLayer()),via.GetDrillValue(),via.GetNetCode())
  report['saved_fixed_barrel_pad_process'].append(dict(uuid=uid,blocked=blocked is not None,records=records))
 report['source_family_sidecars_exact']=all(force._hash(src)==force._hash(candidate.parent/src.name)for src in source.parent.glob('board.*')if src.is_file()and src.name!='board.kicad_pcb')
 if (out/'source-drc.json').exists():
  from collections import Counter
  drca=json.loads((out/'source-drc.json').read_text());drcb=json.loads((out/'drc.json').read_text())
  def signatures(d):return Counter((v['type'],v['severity'],tuple(sorted(i['uuid']for i in v['items'])))for v in d['violations'])
  old,new=signatures(drca),signatures(drcb)
  report['native_DRC_nonregression']=dict(source_count=len(drca['violations']),candidate_count=len(drcb['violations']),
   added_signature_counts=[dict(signature=k,count=v)for k,v in (new-old).items()],removed_signature_counts=[dict(signature=k,count=v)for k,v in (old-new).items()],
   source_unconnected_count=len(drca['unconnected_items']),candidate_unconnected_count=len(drcb['unconnected_items']),not_zero_DRC_qualification=True)
 rebindings={force._item_key(q):force._item_key(af['C37'].FindPadByNumber(q.GetNumber()))for q in bf['C37'].Pads()}
 report['partition_exact_C37_pad_identity_rebindings']={str(k):str(v)for k,v in rebindings.items()}
 try:report['native_partition_pair']=partitions.compare(a,b,timeout_s=5.,identity_rebindings=rebindings)
 except Exception as exc:report['native_partition_pair_refusal']=str(exc)
report.update(board_private_only=True,current_qualified=False,release_authority=False)
assert force._hash(source)==study['peer_sha256']
(out/(args.mode+'.json')).write_text(json.dumps(report,indent=2,default=str)+'\n')
print(json.dumps(dict(mode=args.mode,output=str(out/(args.mode+'.json')),report=report if args.mode in ('refill','receive')else {k:v for k,v in report.items()if k not in ('contact_receiving','native_partition_pair')}),default=str)[:7000])
