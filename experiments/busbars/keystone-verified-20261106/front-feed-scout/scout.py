import sys,json,time,hashlib
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform')
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
from cec_pipeline import bridges
import cec_force_current as force
import cec_fr as fr
from shapely.geometry import box
p,_=_native()
source=ROOT/'experiments/busbars/part-model-20261106/endpoint-first-20261106/vbus-shortcut-v6/candidate/board.kicad_pcb'
sha='4b7457bd28a1a798b6c851b354a2807d02472b8c85b6f583ec48833dce616310'
assert hashlib.sha256(source.read_bytes()).hexdigest()==sha
b=p.LoadBoard(str(source));net='/SENSE12V_HI';width=3230592
case=int(sys.argv[1]);x,y=[(18.35,70.5),(20.75,70.5),(24.0,70.5)][case]
a=(x,y-5.35);z=(x,y+5.35)
body=box(x-2.4384/2,y-12.43/2,x+2.4384/2,y+12.43/2)
lands=[box(xx-1.75,yy-1.3,xx+1.75,yy+1.3)for xx,yy in(a,z)]
geometry,_=bridges.screen_geometry(b,body,lands,dict(id=f'left-front-{case}',face='F.Cu'),net=net,clearance=lambda _:200000,mechanical_margin_nm=200000,deadline=time.monotonic()+2)
links=[]
for label,left,right in [('source',(43.20461,38.5582),a),('header',z,(18.349999,77.4))]:
 cache={};diag={}
 def guard(u,v,half):
  return fr._edge_leg_clear(b,u,v,half) and not force._native_track_rule_hits(b,p.SHAPE_SEGMENT(u,v,width),p.F_Cu,cache=cache)
 legs=fr._guarded_profiled_lastmile_legs(b,p.VECTOR2I_MM(*left),p.VECTOR2I_MM(*right),width,p.F_Cu,200000,b.GetNetcodeFromNetname(net),guard,allow_maze=True,maze_margin_mm=6,foreign_cache=cache,deadline_monotonic=time.monotonic()+1.5,max_length_nm=160000000,refine_maze=True,refinement_grids_mm=(.5,.25),search_diagnostics=diag)
 links.append(dict(name=label,found=bool(legs),diagnostics=diag,legs=[dict(start=[u.x/1e6,u.y/1e6],end=[v.x/1e6,v.y/1e6],width_nm=w)for u,v,w in legs or []]))
r=dict(case=case,source_sha256=sha,feet=[a,z],body_length_mm=12.43,body_width_mm=2.4384,land_size_mm=[3.5,2.6],clearance_nm=200000,feed_width_nm=width,geometry=geometry,links=links,preview_only=True,underside_unknown=True,board_saved=False,synthetic_conductor=False,current_qualified=False,assembled_Z_qualified=False)
assert hashlib.sha256(source.read_bytes()).hexdigest()==sha
out=Path(__file__).parent/f'case-{case}.json';out.write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
