"""Single private zone widening, conservative octilinear envelope, no track additions."""
import sys,json,math,shutil,time,argparse
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_assembly_envelope as assembly
import cec_copper_echo as sexpr
import cec_additive_route_receiving as additive
from shapely.geometry import Polygon,MultiPoint,mapping
from shapely.ops import unary_union
p,_=_native();folder=Path(__file__).parent;source=folder/'hub-C37-vent-v1/candidate/board.kicad_pcb';out=folder/'hub-C37-widen-v1';child=out/'candidate/board.kicad_pcb'
SHA='4825def1abce879355b751406634f2dc5d552c207c779710b3cd6877ecf05992';assert force._hash(source)==SHA
UID='fc65fef1-239d-4859-94dd-f827621e549e';study=json.loads((folder/'Hub-C37-right-widen-corridor.json').read_text());points=study['proposed_centerline_nm']
parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['construct','refill','literal-save','verify']);args=parser.parse_args()
def zone(board):return next(z for z in board.Zones()if force._uid(z)==UID)
def uid(n):return next((c[1].strip('"')for c in n[1:]if isinstance(c,list)and c and c[0]=='uuid'),None)
if args.mode=='construct':
 assert not out.exists(),'refusing existing candidate overwrite';child.parent.mkdir(parents=True)
 for src in source.parent.glob('board.*'):
  if src.is_file():shutil.copy2(src,child.parent/src.name)
 b=p.LoadBoard(str(child));z=zone(b);old=assembly.polygon_from_native(z.Outline())
 # Circumscribed octagon contains the entire 1 mm disk, plus 1 um guard.
 r=501000;d=math.ceil(r*(math.sqrt(2)-1));offsets=[(r,d),(d,r),(-d,r),(-r,d),(-r,-d),(-d,-r),(d,-r),(r,-d)]
 capsules=[]
 for s,t in zip(points,points[1:]):
  capsules.append(MultiPoint([((v[0]+dx)/1e6,(v[1]+dy)/1e6)for v in (s,t)for dx,dy in offsets]).convex_hull)
 added=unary_union(capsules);expanded=old.union(added);assert expanded.geom_type=='Polygon'
 poly=z.Outline();poly.RemoveAllContours()
 poly.NewOutline()
 for x,y in list(expanded.exterior.coords)[:-1]:poly.Append(round(x*1e6),round(y*1e6))
 for ring in expanded.interiors:
  poly.NewHole()
  for x,y in list(ring.coords)[:-1]:poly.Append(round(x*1e6),round(y*1e6),-1,poly.HoleCount(0)-1)
 p.SaveBoard(str(child),b)
 report=dict(source_sha256=SHA,outline_added_area_mm2=expanded.difference(old).area,proposed_outline=mapping(expanded),
  circumscribed_octagon_radius_nm=r,diagonal_offset_nm=d,no_track_additions=True)
elif args.mode=='refill':
 import cec_zone_fill as fill
 b=p.LoadBoard(str(child));report=dict(native_refill=fill.fill_with_report(b));p.SaveBoard(str(child),b)
elif args.mode=='literal-save':
 original=sexpr._parse(sexpr._TOKEN.findall(source.read_text()));native=sexpr._parse(sexpr._TOKEN.findall(child.read_text()))
 replacement=next(n for n in native[1:]if isinstance(n,list)and n and n[0]=='zone'and uid(n)==UID)
 target=next(n for n in original[1:]if isinstance(n,list)and n and n[0]=='zone'and uid(n)==UID)
 fields=('polygon','filled_polygon','fill_segments')
 target[:]=[n for n in target if not isinstance(n,list)or not n or n[0]not in fields]
 target.extend(n for n in replacement[1:]if isinstance(n,list)and n and n[0]in fields)
 child.write_text(additive._render(original)+'\n');report=dict(exact_parent_except_named_zone_outline_and_native_fill=True)
else:
 import cec_native_partition_pair as partitions
 import cec_fr as fr
 a=p.LoadBoard(str(source));b=p.LoadBoard(str(child));za,zb=zone(a),zone(b)
 sa=assembly.polygon_from_native(za.GetFilledPolysList(p.F_Cu));sb=assembly.polygon_from_native(zb.GetFilledPolysList(p.F_Cu))
 nativea,_=force._preservation_snapshot(source);nativeb,_=force._preservation_snapshot(child)
 changed=[u for u in nativea if nativea[u]!=nativeb[u]]
 report=dict(exact_changed_native_ids=changed,only_named_zone_changed=changed==[UID],all_native_ids_exact=set(nativea)==set(nativeb),
  added_actual_fill_area_mm2=sb.difference(sa).area,removed_actual_fill_area_mm2=sa.difference(sb).area,
  root_source_sha256='c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db',
  sidecars_exact=all(force._hash(s)==force._hash(child.parent/s.name)for s in source.parent.glob('board.*')if s.is_file()and s.name!='board.kicad_pcb'))
 legs=[]
 for s,t in zip(points,points[1:]):
  track=p.PCB_TRACK(b);track.SetStart(p.VECTOR2I(*s));track.SetEnd(p.VECTOR2I(*t));track.SetWidth(1000000);track.SetLayer(p.F_Cu)
  capsule=p.SHAPE_POLY_SET();track.TransformShapeToPolygon(capsule,p.F_Cu,0,1000,p.ERROR_OUTSIDE)
  loss=capsule.CloneDropTriangulation();loss.BooleanSubtract(zb.GetFilledPolysList(p.F_Cu))
  lossgeo=assembly.polygon_from_native(loss)
  legs.append(dict(start_nm=s,end_nm=t,native_fullwidth_capsule_loss_area_mm2=lossgeo.area,
   exact_native_fullwidth_contained=loss.OutlineCount()==0,
   foreign_clear=fr._tap_foreign_clear(b,p.VECTOR2I(*s),p.VECTOR2I(*t),1000000,p.F_Cu,200000,{zb.GetNetCode()}),
   edge_clear=fr._edge_leg_clear(b,p.VECTOR2I(*s),p.VECTOR2I(*t),700000),rule_hits=force._native_track_rule_hits(b,track.GetEffectiveShape(p.F_Cu),p.F_Cu)))
 report['native_1mm_corridor_witness']=legs
 pairedstudy=json.loads((folder/'C37-coordinated-translation.json').read_text());atx=p.LoadBoard(str(ROOT/pairedstudy['source']))
 for ref,pose in pairedstudy['ATX_poses'].items():
  fp=atx.FindFootprintByReference(ref);fp.SetOrientationDegrees(pose[2]);fp.SetPosition(p.VECTOR2I(*pose[:2]))
 stack=ROOT/'beta/assembly/hub-atx-stack.json';paired,_=assembly.evaluate_boards(atx,b,json.loads(stack.read_text()))
 report.update(stack_sha256=force._hash(stack),stack_unchanged=force._hash(stack)==pairedstudy['stack_sha256'],paired_ok=paired['ok'],paired_violations=paired['violations'])
 try:report['native_partitions']=partitions.compare(a,b,timeout_s=5.)
 except Exception as exc:report['native_partition_refusal']=str(exc)
 if (out/'drc.json').exists():
  from collections import Counter
  old=json.loads((folder/'hub-C37-vent-v1/drc.json').read_text());new=json.loads((out/'drc.json').read_text())
  def sig(d):return Counter((v['type'],v['severity'],tuple(sorted(i['uuid']for i in v['items'])))for v in d['violations'])
  report['DRC']=dict(source_severities=dict(Counter(v['severity']for v in old['violations'])),candidate_severities=dict(Counter(v['severity']for v in new['violations'])),
   added_signatures=list((sig(new)-sig(old)).items()),removed_signatures=list((sig(old)-sig(new)).items()),source_opens=len(old['unconnected_items']),candidate_opens=len(new['unconnected_items']))
 import cec_zone_fill as fill
 def fills(board):
  return {(force._uid(z),int(face)):z.GetFilledPolysList(face).Format()for z in board.Zones()if not z.GetIsRuleArea()for face in z.GetLayerSet().CuStack()if z.HasFilledPolysForLayer(face)}
 probe=p.LoadBoard(str(child));savedfills=fills(probe);refilled=fill.fill_with_report(probe);freshfills=fills(probe)
 report['independent_saved_full_native_refill_replay']=dict(report=refilled,all_saved_fills_exact=savedfills==freshfills,
  changed_zone_layers=[str(key)for key in savedfills.keys()|freshfills.keys()if savedfills.get(key)!=freshfills.get(key)],board_resaved=False)
report.update(candidate_sha256=force._hash(child),source_sha256=SHA,global_current_qualified=False,thermal_qualified=False,admitted=False,release_authority=False)
assert force._hash(source)==SHA
(out/(args.mode+'.json')).write_text(json.dumps(report,indent=2,default=str)+'\n')
print(json.dumps({k:v for k,v in report.items()if k not in ('proposed_outline','native_partitions')},default=str)[:6500])
