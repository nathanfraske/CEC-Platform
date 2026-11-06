"""Four deliberate short-bridge topology checks; native RAM only."""
import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
p,_=_native()
import cec_force_current as f,cec_fr as fr,cec_assembly_envelope as assembly
from shapely.geometry import box
S=ROOT/'experiments/busbars/part-model-20261106/endpoint-first-20261106/vbus-shortcut-v6/candidate/board.kicad_pcb'
assert f._hash(S)=='4b7457bd28a1a798b6c851b354a2807d02472b8c85b6f583ec48833dce616310'
b=p.LoadBoard(str(S));net='/SENSE12V_HI';width=3230592;face=p.B_Cu;gap=fr._foreign_clearance_resolver(b)
objects=[*b.GetTracks(),*(pad for fp in b.GetFootprints()for pad in fp.Pads())]
holder=p.FOOTPRINT(b);pad=p.PAD(holder);holder.Add(pad);pad.SetShape(p.PAD_SHAPE_RECT);pad.SetSize(p.VECTOR2I_MM(3.5,3.5));layers=p.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
zones=[(z,assembly.polygon_from_native(z.GetFilledPolysList(face)))for z in b.Zones()if not z.GetIsRuleArea()and z.IsOnLayer(face)and z.GetNetname()!=net and z.GetFilledPolysList(face).OutlineCount()]
poses=[('jump_5Vbank_J3_11',(18.349999,64.8),(18.349999,75.5)),('jump_5Vbank_interpin',(20,64.8),(20,75.5)),('jump_5Vbank_J3_10',(22.549999,64.8),(22.549999,75.5)),('jump_3V3_vertical',(14.55,60),(3.85,60))]
rows=[]
for name,a,z in poses:
 vertical=a[0]==z[0]
 sx,sy=(3.5,2.6)if vertical else(2.6,3.5)
 pad.SetSize(p.VECTOR2I_MM(sx,sy))
 feet=[]
 for x,y in (a,z):
  pad.SetPosition(p.VECTOR2I_MM(x,y));hits=[]
  for item in objects:
   if item.IsOnLayer(face)and item.GetNetname()!=net and pad.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face),max(500000,int(gap(item,face)))):
    h=dict(uuid=f._uid(item),net=item.GetNetname(),kind=item.GetClass())
    if item.GetClass()=='PAD':h.update(ref=item.GetParentFootprint().GetReference(),pad=item.GetNumber())
    hits.append(h)
  xy=box(x-sx/2,y-sy/2,x+sx/2,y+sy/2).buffer(.5)
  feet.append(dict(at_mm=[x,y],foreign_items=hits,foreign_fill=[dict(uuid=f._uid(q),net=q.GetNetname(),area_mm2=xy.intersection(g).area)for q,g in zones if xy.intersects(g)]))
 links=[]
 for label,left,right in [('upper',(18.6,36),a),('lower',z,(18.349999,77.4))]:
  cache={};diag={};start=time.monotonic()
  def guard(u,v,half):return fr._edge_leg_clear(b,u,v,half)and not f._native_track_rule_hits(b,p.SHAPE_SEGMENT(u,v,width),face,cache=cache)
  legs=fr._guarded_profiled_lastmile_legs(b,p.VECTOR2I_MM(*left),p.VECTOR2I_MM(*right),width,face,200000,b.GetNetcodeFromNetname(net),guard,allow_maze=True,maze_margin_mm=6.,foreign_cache=cache,deadline_monotonic=time.monotonic()+7.,max_length_nm=110000000,refine_maze=True,refinement_grids_mm=(.5,.25),search_diagnostics=diag)
  links.append(dict(name=label,found=bool(legs),elapsed_s=time.monotonic()-start,legs=[dict(start_mm=[u.x/1e6,u.y/1e6],end_mm=[v.x/1e6,v.y/1e6],width_nm=w)for u,v,w in legs or []],diagnostics=diag))
 row=dict(name=name,feet=feet,links=links);rows.append(row);print(name,[(len(q['foreign_items']),len(q['foreign_fill']))for q in feet],[(q['name'],q['found'])for q in links],flush=True)
(Path(__file__).parent/'receipt.json').write_text(json.dumps(dict(source_sha256=f._hash(S),net=net,land_pitch_mm=10.7,provisional_land_axial_mm=2.6,provisional_land_transverse_mm=3.5,land_foreign_clearance_mm=.5,pcb_width_mm=width/1e6,poses=rows,scope='Four finite RAM-only topology screens; no native save, body/tail/Z/joint/current qualification or exhaustive no-path proof'),indent=2)+'\n')
