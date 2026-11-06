"""Three short full-current BCu links for two inline raised bars; RAM only."""
exec((__import__('pathlib').Path(__file__).parent/'probe.py').read_text().split('endpoints=')[0])
import time
rows=[]
for name,a,z in [('upper_source_hook',(18.6,36),(4,32.1)),('middle',(4,57.5),(4,60)),('lower_source_hook',(4,80.32),(11.4,85.2))]:
 cache={};diag={};start=time.monotonic()
 def guard(a,z,half):return fr._edge_leg_clear(b,a,z,half)and not f._native_track_rule_hits(b,p.SHAPE_SEGMENT(a,z,width),p.B_Cu,cache=cache)
 legs=fr._guarded_profiled_lastmile_legs(b,p.VECTOR2I_MM(*a),p.VECTOR2I_MM(*z),width,p.B_Cu,200000,b.GetNetcodeFromNetname(net),guard,
  allow_maze=True,maze_margin_mm=4.,foreign_cache=cache,deadline_monotonic=time.monotonic()+8.,max_length_nm=60000000,refine_maze=True,refinement_grids_mm=(.5,.25),search_diagnostics=diag)
 row=dict(name=name,found=bool(legs),elapsed_s=time.monotonic()-start,diagnostics=diag,legs=[dict(start_mm=[u.x/1e6,u.y/1e6],end_mm=[v.x/1e6,v.y/1e6],width_nm=w)for u,v,w in legs or []]);rows.append(row);print(name,row['found'],row['legs'],flush=True)
holes=[]
for fp in b.GetFootprints():
 for pad in fp.Pads():
  if pad.GetDrillSize().x and pad.GetPosition().x<12000000:holes.append(dict(ref=fp.GetReference(),at_mm=[pad.GetPosition().x/1e6,pad.GetPosition().y/1e6],drill_mm=[pad.GetDrillSize().x/1e6,pad.GetDrillSize().y/1e6],pad_mm=[pad.GetSize().x/1e6,pad.GetSize().y/1e6]))
(Path(__file__).parent/'route-probe.json').write_text(json.dumps(dict(source_sha256=f._hash(S),results=rows,left_drilled_pads=holes,scope='RAM source-hook feasibility; no current transport, body/tail or assembly qualification'),indent=2)+'\n')
