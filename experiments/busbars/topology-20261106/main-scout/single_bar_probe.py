"""Two requested single-bar topologies, RAM-only ordinary-track counterfactual."""
exec((__import__('pathlib').Path(__file__).parent/'probe.py').read_text().split('endpoints=')[0])
import time
import cec_ordinary_route_receiving as ordinary
uid='6bae995b-213f-49bb-af9b-7daee096b494'
held=[t for t in b.GetTracks()if f._uid(t)==uid];assert len(held)==1
ordinary_net=held[0].GetNetname();assert ordinary_net in ordinary.eligible_nets(b,S,'atx-24pin-rev3')
b.Remove(held[0]);rows=[]
for x in (20,22):
 for name,a,z in [('upper_to_source',(x,34.6),(18.6,36)),('lower_to_J3_10',(x,60),(22.549999,77.4)),('lower_to_J3_11',(x,60),(18.349999,77.4))]:
  cache={};diag={};start=time.monotonic()
  def guard(a,z,half):return fr._edge_leg_clear(b,a,z,half)and not f._native_track_rule_hits(b,p.SHAPE_SEGMENT(a,z,width),p.B_Cu,cache=cache)
  legs=fr._guarded_profiled_lastmile_legs(b,p.VECTOR2I_MM(*a),p.VECTOR2I_MM(*z),width,p.B_Cu,200000,b.GetNetcodeFromNetname(net),guard,
   allow_maze=True,maze_margin_mm=6.,foreign_cache=cache,deadline_monotonic=time.monotonic()+8.,max_length_nm=100000000,refine_maze=True,refinement_grids_mm=(.5,.25),search_diagnostics=diag)
  row=dict(bar_x_mm=x,name=name,found=bool(legs),elapsed_s=time.monotonic()-start,diagnostics=diag,legs=[dict(start_mm=[u.x/1e6,u.y/1e6],end_mm=[v.x/1e6,v.y/1e6],width_nm=w)for u,v,w in legs or []]);rows.append(row);print(x,name,row['found'],row['legs'],flush=True)
(Path(__file__).parent/'single-bar-probe.json').write_text(json.dumps(dict(source_sha256=f._hash(S),net=net,width_nm=width,ram_removed=dict(uuid=uid,net=ordinary_net,positive_existing_ordinary_eligibility=True),results=rows,scope='Two finite requested BCu topologies; no saved board, route/current/transport admission or exhaustive impossibility claim'),indent=2)+'\n')
