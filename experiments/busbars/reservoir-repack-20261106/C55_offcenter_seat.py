"""Exact pad erosion / native copper difference, then one nearest grid seat."""
import sys,json,math
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_assembly_envelope as assembly
import cec_fab_profile as fab
import cec_fr as fr
import cec_decoupler_cell as cells
from shapely.geometry import Point,mapping,box
p,_=_native();folder=Path(__file__).parent;record=json.loads((folder/'geometry-map-derived-seven.json').read_text());source=ROOT/record['source'];assert force._hash(source)==record['source_sha256'];b=p.LoadBoard(str(source));fps={f.GetReference():f for f in b.GetFootprints()}
conditional='--omit-MUX-diagonal-diagnostic'in sys.argv
omitted_trace=None
if conditional:
 held=list(b.GetTracks());omitted_trace=next(t for t in held if force._uid(t)=='25bba609-ee8a-4547-9df7-c906cfc0979c');b.Remove(omitted_trace)
for ref,pose in record['proposed_poses'].items():fps[ref].SetOrientationDegrees(pose[2]);fps[ref].SetPosition(p.VECTOR2I(pose[0],pose[1]))
pad=next(q for q in fps['C55'].Pads()if q.GetNumber()=='2');code=pad.GetNetCode();poly=assembly.polygon_from_native(pad.GetEffectivePolygon(p.F_Cu));margin=.001;region=poly.buffer(-(.25+margin),quad_segs=64);eroded=region;constraint_rows=[];local=region.buffer(.46).envelope
def subtract(g,identity,offset):
 global region
 if g.is_empty or not g.intersects(local):return
 before=region.area;region=region.difference(g.buffer(offset,quad_segs=64))
 if region.area<before-1e-12:constraint_rows.append(dict(identity=identity,removed_area_mm2=before-region.area,offset_mm=offset))
layers=list(b.GetEnabledLayers().CuStack())
for z in b.Zones():
 if z.GetIsRuleArea()or z.GetNetCode()==code:continue
 for l in layers:
  if not z.IsOnLayer(l):continue
  if z.IsFilled()and z.HasFilledPolysForLayer(l):subtract(assembly.polygon_from_native(z.GetFilledPolysList(l)),dict(uuid=force._uid(z),kind='saved_filled_zone',net=z.GetNetname(),layer=b.GetLayerName(l)),.451)
  if fr._zone_is_route_reservation(b,z,l):subtract(assembly.polygon_from_native(z.Outline()),dict(uuid=force._uid(z),kind='reserved_zone_outline',net=z.GetNetname(),layer=b.GetLayerName(l)),.451)
for item in [*(q for fp in b.GetFootprints()for q in fp.Pads()),*b.GetTracks()]:
 if force._uid(item)==force._uid(pad):continue
 if item.GetClass()!='PAD'and item.GetNetCode()==code:continue
 bb=item.GetBoundingBox();bounds=box(bb.GetLeft()/1e6,bb.GetTop()/1e6,bb.GetRight()/1e6,bb.GetBottom()/1e6)
 if not bounds.intersects(local):continue
 for l in layers:
  if not item.IsOnLayer(l):continue
  if item.GetClass()=='PAD':g=assembly.polygon_from_native(item.GetEffectivePolygon(l))
  else:
   native=p.SHAPE_POLY_SET();item.TransformShapeToPolygon(native,l,0,1000,p.ERROR_OUTSIDE);g=assembly.polygon_from_native(native)
  subtract(g,dict(uuid=force._uid(item),kind=item.GetClass(),net=item.GetNetname(),layer=b.GetLayerName(l)),.451 if item.GetNetCode()!=code else .251)
grid=.01;cx,cy=pad.GetPosition().x/1e6,pad.GetPosition().y/1e6;sites=[]
if not region.is_empty:
 left,top,right,bottom=region.bounds
 for ix in range(math.ceil(left/grid),math.floor(right/grid)+1):
  for iy in range(math.ceil(top/grid),math.floor(bottom/grid)+1):
   x,y=round(ix*grid,6),round(iy*grid,6)
   if region.covers(Point(x,y)):sites.append((math.hypot(x-cx,y-cy),x,y))
sites.sort();verified=None
if sites:
 _,x,y=sites[0];at=p.VECTOR2I_MM(x,y);blocked,recs=fab.via_at_pad_conflicts(b,at,500000,300000,code);guard={};clear=fr._via_spot_clear(b,at,500000,200000,{code},drill_nm=300000,net_code=code,foreign_cache={},report=guard);holes=cells._hole_to_hole_clear(b,at,.3);edge=fr._edge_leg_clear(b,at,at,250000);rules=force._native_track_rule_hits(b,p.SHAPE_SEGMENT(at,at,500000),p.F_Cu);verified=dict(at_mm=[x,y],distance_from_pad_center_mm=sites[0][0],native_pad_process_clear=blocked is None,native_pad_process_records=recs,all_layer_clear=clear,all_layer_guard=guard,hole_clear=holes,edge_guard=edge,front_rule_hits=rules,polygon_containment_margin_lower_bound_mm=Point(x,y).distance(poly.boundary)-.25,all_requested_native_guards_pass=blocked is None and clear and holes[0] and edge and not rules)
left,top,right,bottom=poly.bounds
# A larger-than-real centre region gives a stronger no-seat result: ignore
# round corners and the 1um reserve entirely. Use an INSIDE track polygon and
# inscribed circular offsets, so obstacles are not enlarged to fake refusal.
optimistic=box(left+.25,top+.25,right-.25,bottom-.25)
z=next(z for z in b.Zones()if force._uid(z)=='2bf47d0a-918a-48da-9713-1fa59bf7fd2b')
optimistic=optimistic.difference(assembly.polygon_from_native(z.GetFilledPolysList(p.B_Cu)).buffer(.45,quad_segs=128));after_zone=optimistic
trace=omitted_trace if conditional else next(t for t in b.GetTracks()if force._uid(t)=='25bba609-ee8a-4547-9df7-c906cfc0979c');native=p.SHAPE_POLY_SET();trace.TransformShapeToPolygon(native,p.B_Cu,0,1,p.ERROR_INSIDE)
if not conditional:optimistic=optimistic.difference(assembly.polygon_from_native(native).buffer(.45,quad_segs=128))
out=dict(source=record['source'],source_sha256=record['source_sha256'],peer_sha256=record['peer_sha256'],stack_sha256=record['stack_sha256'],fixed_poses=record['proposed_poses'],pad_uuid=force._uid(pad),pad_polygon=mapping(poly),via_geometry_mm=[.5,.3],clearance_mm=.2,containment_reserve_mm=margin,eroded_native_pad_center_region=mapping(eroded),remaining_conservative_center_region=mapping(region),remaining_region_area_mm2=region.area,remaining_region_bounds_mm=list(region.bounds)if not region.is_empty else None,active_geometric_constraints=constraint_rows,grid_mm=grid,grid_sites_inside_derived_region=len(sites),native_verified_seat=verified,optimistic_zero_margin_superset_after_3V3_zone=mapping(after_zone),optimistic_zero_margin_superset_after_3V3_zone_area_mm2=after_zone.area,optimistic_zero_margin_superset_after_MUX_trace_area_mm2=optimistic.area,no_geometric_seat_even_in_optimistic_zero_margin_superset=optimistic.is_empty,closing_trace=dict(uuid=force._uid(trace),net=trace.GetNetname(),layer=trace.GetLayerName(),start_nm=list(trace.GetStart()),end_nm=list(trace.GetEnd()),width_nm=trace.GetWidth(),locked=trace.IsLocked()),source_copper_cut=False,antipad_or_foreign_copper_subtraction_authorized=False,board_saved=False,new_candidate_saved=False,release_authority=False,full_source_owned_construction_and_saved_receiving_pending=True)
out['conditionally_omitted_in_RAM_uuids']=[force._uid(omitted_trace)]if conditional else[]
out['conditional_is_not_cut_permission']=True
assert force._hash(source)==record['source_sha256'];(folder/('C55-offcenter-seat-conditional-MUX-rebuild.json'if conditional else 'C55-offcenter-seat.json')).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k not in ['fixed_poses','pad_polygon','eroded_native_pad_center_region','remaining_conservative_center_region','optimistic_zero_margin_superset_after_3V3_zone']},indent=2))
