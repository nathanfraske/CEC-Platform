"""One hand-derived 1 mm full-width right-side corridor; no board mutation."""
import sys,json,time,math
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_assembly_envelope as assembly
import cec_fr as fr
from shapely.geometry import LineString,mapping,box
from shapely.ops import unary_union
p,_=_native();folder=Path(__file__).parent;source=folder/'hub-C37-vent-v1/candidate/board.kicad_pcb'
assert force._hash(source)=='4825def1abce879355b751406634f2dc5d552c207c779710b3cd6877ecf05992'
b=p.LoadBoard(str(source));zone=next(z for z in b.Zones()if force._uid(z)=='fc65fef1-239d-4859-94dd-f827621e549e');nc=zone.GetNetCode()
points=[(75301000,37151000),(75950000,37800000),(75950000,47300000),(75301000,47949000)]
rows=[];polys=[];deadline=time.monotonic()+7.
for s,t in zip(points,points[1:]):
 leg=p.PCB_TRACK(b);leg.SetStart(p.VECTOR2I(*s));leg.SetEnd(p.VECTOR2I(*t));leg.SetWidth(1000000);leg.SetLayer(p.F_Cu);leg.SetNetCode(nc)
 poly=p.SHAPE_POLY_SET();leg.TransformShapeToPolygon(poly,p.F_Cu,0,1000,p.ERROR_OUTSIDE);polys.append(assembly.polygon_from_native(poly))
 blockers=[]
 for obj in [*b.GetTracks(),*(q for fp in b.GetFootprints()for q in fp.Pads())]:
  if not obj.IsOnLayer(p.F_Cu)or obj.GetNetCode()==nc:continue
  if leg.GetEffectiveShape(p.F_Cu).Collide(obj.GetEffectiveShape(p.F_Cu),200000):
   blockers.append(dict(uuid=force._uid(obj),kind=obj.GetClass(),net=obj.GetNetname(),
    ref=obj.GetParentFootprint().GetReference()if obj.GetClass()=='PAD'else None,
    pin=obj.GetNumber()if obj.GetClass()=='PAD'else None))
 rows.append(dict(start_nm=s,end_nm=t,full_width_nm=1000000,clearance_nm=200000,
  native_foreign_clear=fr._tap_foreign_clear(b,p.VECTOR2I(*s),p.VECTOR2I(*t),1000000,p.F_Cu,200000,{nc}),
  native_edge_clear=fr._edge_leg_clear(b,p.VECTOR2I(*s),p.VECTOR2I(*t),700000),
  native_rule_hits=force._native_track_rule_hits(b,leg.GetEffectiveShape(p.F_Cu),p.F_Cu),authored_foreign_blockers=blockers))
corridor=unary_union(polys);savedfillhits=[]
for z in b.Zones():
 if z.GetIsRuleArea()or z.GetNetCode()==nc or not z.HasFilledPolysForLayer(p.F_Cu):continue
 actual=assembly.polygon_from_native(z.GetFilledPolysList(p.F_Cu));hit=corridor.buffer(.2).intersection(actual)
 if not hit.is_empty:savedfillhits.append(dict(uuid=force._uid(z),net=z.GetNetname(),area_mm2=hit.area,bounds_mm=list(hit.bounds),requires_separate_native_refill_and_current_check=True))
actual=assembly.polygon_from_native(zone.GetFilledPolysList(p.F_Cu))
outline=assembly.polygon_from_native(zone.Outline())
expanded=outline.union(corridor)
window=box(74.5,37.,76.6,48.2)
out=dict(source=str(source.relative_to(ROOT)),source_sha256=force._hash(source),zone_uuid=force._uid(zone),net=zone.GetNetname(),
 proposed_centerline_nm=points,width_nm=1000000,clearance_nm=200000,legs=rows,
 proposed_expanded_zone_outline=mapping(expanded),added_outline_region=mapping(expanded.difference(outline)),
 source_filled_local_geometry=mapping(actual.intersection(window)),saved_foreign_fill_obligations=savedfillhits,
 path_basis='One right-hand 1 mm capsule corridor with 45-degree joins into existing 1.002 mm rail above/below the C37 Ground cutout. This is proposed zone area, not synthetic conductor copper or a saved track.',
 board_saved=False,zone_outline_edited=False,global_current_qualified=False,release_authority=False)
(folder/'Hub-C37-right-widen-corridor.json').write_text(json.dumps(out,indent=2,default=str)+'\n')
print(json.dumps({k:v for k,v in out.items()if k not in ('proposed_expanded_zone_outline','added_outline_region','source_filled_local_geometry')},default=str))
