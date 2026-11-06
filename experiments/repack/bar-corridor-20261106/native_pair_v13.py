"""Explicit native-macro divider trial; routes consume fresh native requests."""
import argparse,json,math,shutil,time
from pathlib import Path
from cec_pipeline.native import _native
p,_=_native()
from cec_pipeline import cells,construction,geometry
import cec_fr as fr,cec_force_current as force
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler,cec_additive_route_receiving as additive
R=Path(__file__).resolve().parent

def soften(points):
 out=[points[0]]
 for a,b,c in zip(points,points[1:],points[2:]):
  u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1])
  if u[0]*v[0]+u[1]*v[1]==0:
   step=min(30000,max(map(abs,u))//3,max(map(abs,v))//3)
   out.extend([tuple(b[j]-(int(math.copysign(step,u[j]))if u[j]else 0)for j in(0,1)),tuple(b[j]+(int(math.copysign(step,v[j]))if v[j]else 0)for j in(0,1))])
  else:out.append(b)
 out.append(points[-1]);geometry.path([list(v)for v in out],minimum_phase_nm=20000)
 return [list(v)for v in out]

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',required=True);ap.add_argument('--sha256',required=True);ap.add_argument('--name',default='native-pair-v13');ap.add_argument('--construct',action='store_true');ap.add_argument('--preview',action='store_true');ap.add_argument('--preflight',action='store_true');ap.add_argument('--r56-rotation',type=int,choices=(90,270),default=90);ap.add_argument('--r56-y',type=float,default=56.7);ap.add_argument('--r56-x',type=float,default=28.9);ap.add_argument('--locked-transport',action='append',default=[]);ap.add_argument('--locked-cut',action='append',default=[]);args=ap.parse_args()
 source=Path(args.source).resolve();assert force._hash(source)==args.sha256
 target=R/args.name/'board.kicad_pcb';assert not target.exists()
 op=dict(kind='place_cell',native_macro=True,poses=[dict(reference=ref,at_nm=at,rotation_deg=90 if ref=='R55'else args.r56_rotation)for ref,at in [('R55',[27200000,56700000]),('R56',[round(args.r56_x*1e6),round(args.r56_y*1e6)])]],routes=[],vias=[],allow_locked_footprint_uuids=[],allow_locked_track_uuids=args.locked_cut,allow_locked_transport_uuids=args.locked_transport,reference_group_uuids=['a1dea770-31b1-5e49-b8de-f601e2e38253'])
 if args.preview:
  result=cells.preview(source,op,'atx-24pin-rev3');target.parent.mkdir(parents=True,exist_ok=True)
  (target.parent/'preview.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k in('required_locked_cut_uuids','required_locked_transport_uuids','ok','complete')}));return
 parent=p.LoadBoard(str(source));frame,packet,transported=cells.compile_macro(parent,op,'atx-24pin-rev3')
 target.parent.mkdir(parents=True,exist_ok=True)
 (target.parent/'packet.json').write_text(json.dumps(packet,indent=2)+'\n')
 if args.preflight:
  prefill=compiler.pre_refill_barrel_screen(frame,packet,timeout_s=10.)
  additive._ground_refill(frame)
  pose=compiler.native_pose_screen(parent,frame,packet,timeout_s=10.,phase_timeouts_s=(10.,)*3)
  (target.parent/'pre-route-native-pose.json').write_text(json.dumps(dict(prefill=prefill,pose=pose),indent=2)+'\n')
  if not prefill['ok']or not pose['ok']:print(json.dumps(dict(native_preflight=False,board_written=False)));return
 requests=sorted(packet['requests'].items(),key=lambda row:(-int(row[1].get('width_nm',0)),row[0]))
 routed=[];unresolved=[]
 for key,req in requests:
  if req.get('kind')not in('source_boundary','supply_departure'):continue
  retained=escape.retained_native_boundary_connection(frame,req,timeout_s=2.)
  if retained:
   routed.append(dict(request=key,existing_native_path=retained));continue
  if not all(isinstance(req.get(port),dict)and 'at_nm'in req[port]for port in('a','b')):
   unresolved.append(dict(request=key,reason='typed_port_requires_explicit_authoring',value=req));continue
  a,z=[tuple(req[port]['at_nm'])for port in('a','b')];net=req['net'];w=req['width_nm'];nc=frame.GetNetcodeFromNetname(net)
  if a==z:continue
  allowed=set(req['a'].get('layers',[]))&set(req['b'].get('layers',[]));found=None
  for face in(p.F_Cu,p.B_Cu,p.In2_Cu,p.In3_Cu):
   if face not in allowed:continue
   cache={}
   def guard(left,right,half):return fr._edge_leg_clear(frame,left,right,(w+1)//2)and not force._native_track_rule_hits(frame,p.SHAPE_SEGMENT(left,right,w),face,cache=cache)
   legs=fr._guarded_profiled_lastmile_legs(frame,p.VECTOR2I(*a),p.VECTOR2I(*z),w,face,200000,nc,guard,allow_maze=True,maze_margin_mm=3.,foreign_cache=cache,deadline_monotonic=time.monotonic()+9.,max_length_nm=25000000,refine_maze=True,refinement_grids_mm=(.2,.1))
   if not legs:continue
   try:
    pts=soften([tuple(legs[0][0])]+[tuple(row[1])for row in legs]);route=dict(net=net,layer=frame.GetLayerName(face),width_nm=w,points_nm=pts)
    cells.emit_connections(frame,[route],[],identity='native-divider-request:'+key);found=route;break
   except ValueError:continue
  if found:routed.append(dict(request=key,route=found));op['routes'].append(found)
  else:unresolved.append(dict(request=key,reason='bounded_native_route_not_found',value=req))
 (target.parent/'route-plan.json').write_text(json.dumps(dict(source=str(source),sha256=args.sha256,transported_source_copper_uuids=transported,routed=routed,unresolved=unresolved,operation=op),indent=2)+'\n')
 if unresolved or not args.construct:print(json.dumps(dict(unresolved=len(unresolved),routed=len(routed),board_written=False)));return
 for f in source.parent.glob('board.*'):
  if f.is_file():shutil.copy2(f,target.parent/f.name)
 result=construction._construct(source,target,dict(operations=[op]),'atx-24pin-rev3')
 (target.parent/'construction.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(candidate=str(target),sha256=force._hash(target),not_received=True)))

if __name__=='__main__':main()
