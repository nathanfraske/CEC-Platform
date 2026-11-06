"""One geometry-derived +Y Hub C37 translation; RAM only, not routing authority."""
import sys,json,math,time
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_assembly_envelope as assembly
import cec_control_gate_bias_placement as native
import cec_board_geometry as geometry
import cec_fab_profile as fab
import cec_current_topology as topology
from shapely.geometry import shape
from shapely.affinity import affine_transform,translate
p,_=_native();folder=Path(__file__).parent
study=json.loads((folder/'geometry.json').read_text());root=json.loads((folder/'C51-clearance-root.json').read_text())
source=ROOT/study['source'];peer=ROOT/study['peer'];stack=ROOT/study['stack']
assert force._hash(source)==study['source_sha256'] and force._hash(peer)==study['peer_sha256']
b=p.LoadBoard(str(source));hub=p.LoadBoard(str(peer));contract=json.loads(stack.read_text())
for ref,pose in root['cases'][0]['actual_target_poses'].items():
 fp=b.FindFootprintByReference(ref);fp.SetOrientationDegrees(pose[2]);fp.SetPosition(p.VECTOR2I(*pose[:2]))
spec=dict(contract.get('envelopes',{}))
for group in contract['envelope_groups']:
 for key in group['footprints']:spec[key]={k:v for k,v in group.items()if k!='footprints'}
ad=assembly.extract(b,spec);hd=assembly.extract(hub,spec)
cs=shape(next(q for q in ad['bodies']if q['ref']=='C51')['xy'])
c37=next(q for q in hd['bodies']if q['ref']=='C37');projected=affine_transform(shape(c37['xy']),contract['transform'])
lo,hi=0.,1.
for _ in range(40):
 mid=(lo+hi)/2
 if cs.distance(translate(projected,0,mid))<=2*contract['xy_allowance_each_mm']+1e-8:lo=mid
 else:hi=mid
delta_nm=math.ceil(hi/.05)*50000
cap=hub.FindFootprintByReference('C37');oldpose=[*cap.GetPosition(),cap.GetOrientationDegrees()]
oldcourt=assembly.footprint_planar_envelope(cap)[0];neighbors=[]
for fp in hub.GetFootprints():
 if fp.GetReference()=='C37' or fp.GetLayer()!=cap.GetLayer():continue
 try:g=assembly.footprint_planar_envelope(fp)[0]
 except ValueError:continue
 neighbors.append(dict(ref=fp.GetReference(),source_courtyard_distance_mm=oldcourt.distance(g)))
contacts={q.GetNumber():dict(pad_uuid=force._uid(q),net=q.GetNetname(),at_nm=list(q.GetPosition()),
 native_contacts=native._direct_contacts(hub,q,time.monotonic()+3.))for q in cap.Pads()}
cap.SetPosition(p.VECTOR2I(oldpose[0],oldpose[1]+delta_nm));court=assembly.footprint_planar_envelope(cap)[0];clashes=[]
posed_contacts={q.GetNumber():native._direct_contacts(hub,q,time.monotonic()+3.)for q in cap.Pads()}
foreign=[];process=[];zone_hits=[]
for pad in cap.Pads():
 for face in pad.GetLayerSet().CuStack():
  land=assembly.polygon_from_native(pad.GetEffectivePolygon(face))
  for zone in hub.Zones():
   if zone.GetIsRuleArea()or zone.GetNetCode()==pad.GetNetCode()or not zone.IsOnLayer(face)or not zone.HasFilledPolysForLayer(face):continue
   copper=assembly.polygon_from_native(zone.GetFilledPolysList(face))
   if land.distance(copper)<.2-1e-9:zone_hits.append(dict(pad=pad.GetNumber(),zone_uuid=force._uid(zone),net=zone.GetNetname(),layer=int(face),clearance_mm=land.distance(copper)))
 for item in [*hub.GetTracks(),*(q for fp in hub.GetFootprints()for q in fp.Pads())]:
  if item.GetNetCode()==pad.GetNetCode():continue
  for face in pad.GetLayerSet().CuStack():
   if not item.IsOnLayer(face):continue
   s=pad.GetEffectiveShape(face)
   hit=s.Collide(item.GetPosition(),item.GetWidth(face)//2+200000)if item.GetClass()=='PCB_VIA'else s.Collide(item.GetEffectiveShape(face),200000)
   if hit:foreign.append(dict(pad=pad.GetNumber(),item_uuid=force._uid(item),kind=item.GetClass(),net=item.GetNetname(),layer=int(face)))
for uid in ('434aa75c-5627-464e-9437-06fb40f2f600','ee3f11eb-6272-4635-b0a8-5ff97b44ce1e'):
 via=next(t for t in hub.GetTracks()if force._uid(t)==uid)
 blocked,records=fab.via_at_pad_conflicts(hub,via.GetPosition(),via.GetWidth(via.TopLayer()),via.GetDrillValue(),via.GetNetCode())
 process.append(dict(via_uuid=uid,blocked=blocked is not None,records=records))
domains=topology.board_current_domains(hub,peer);widths=topology.route_width_contracts(hub,board_hint=peer)
for fp in hub.GetFootprints():
 if fp.GetReference()=='C37' or fp.GetLayer()!=cap.GetLayer():continue
 try:g=assembly.footprint_planar_envelope(fp)[0]
 except ValueError:continue
 hit=court.intersection(g)
 if not hit.is_empty:clashes.append(dict(ref=fp.GetReference(),area_mm2=hit.area,bounds_mm=list(hit.bounds)))
paired,_=assembly.evaluate_boards(b,hub,contract)
material=assembly.polygon_from_native(geometry.outline_material(hub));edgegap=court.distance(material.boundary)
out=dict(source=study['source'],source_sha256=study['source_sha256'],peer=study['peer'],peer_sha256=study['peer_sha256'],
 stack_sha256=study['stack_sha256'],ATX_poses=root['cases'][0]['actual_target_poses'],
 choice='Hub +Y moves projected C37 away from C51, away from C1 above; R38 remains separated in X. One derived pose only.',
 continuous_positive_Y_separation_threshold_mm=hi,grid_mm=.05,translation_nm=[0,delta_nm],
 C37_source_pose=oldpose,C37_proposed_pose=[*cap.GetPosition(),cap.GetOrientationDegrees()],
 projected_C51_C37_body_distance_mm=cs.distance(translate(projected,0,delta_nm/1e6)),
 required_two_XY_allowance_mm=2*contract['xy_allowance_each_mm'],
 nearest_source_neighbors=sorted(neighbors,key=lambda r:r['source_courtyard_distance_mm'])[:8],
 C37_courtyard_clashes=clashes,C37_courtyard_contained_by_board=material.covers(court),C37_courtyard_edge_gap_mm=edgegap,
 paired_ok=paired['ok'],paired_violations=paired['violations'],C37_source_pad_contacts=contacts,
 C37_posed_pad_contacts=posed_contacts,posed_pad_foreign_200um_conflicts=foreign,retained_barrel_pad_process=process,
 posed_pad_saved_filled_zone_200um_conflicts=zone_hits,
 all_original_contact_ids_preserved=all({x['item_uuid']for x in v['native_contacts']}<={x['item_uuid']for x in posed_contacts[pin]}for pin,v in contacts.items()),
 source_current_domains={net:domains.get(net)for net in sorted({r['net']for r in contacts.values()})},
 source_width_contracts={net:widths.get(net)for net in sorted({r['net']for r in contacts.values()})},
 connected_net_names=sorted({r['net']for r in contacts.values()}),
 copper_retained_unrouted=True,board_saved=False,cut_authority=False,current_qualified=False,release_authority=False)
out['remaining_receiving_obligations']='Fresh saved/refilled receiving, current/planes/nonregression and native old-to-new C37 vent reservation replacement still required. No current authority was synthesized from the existing 1 mm strokes. Existing contacts remain, so no reroute cut is proposed.'
assert force._hash(source)==study['source_sha256'] and force._hash(peer)==study['peer_sha256']
(folder/'C37-coordinated-translation.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items()if k not in ['C37_source_pad_contacts','ATX_poses']},indent=2))
